#!/usr/bin/env python3
"""Host-only FS-021 supervisor. No Django, DB, providers or operational services."""

import argparse
import hashlib
import json
import math
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

GIB = 1024**3


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def event(directory, kind, **details):
    with (directory / "supervisor.jsonl").open("a") as stream:
        stream.write(json.dumps(dict(time=time.time(), kind=kind, **details)) + "\n")


def sensors(root=Path("/sys/class/hwmon")):
    readings = {"cpu": [], "nvme": []}
    identities = []
    for device in root.glob("hwmon*"):
        try:
            driver = (device / "name").read_text().strip()
            for label in device.glob("temp*_label"):
                name = label.read_text().strip()
                kind = (
                    "cpu"
                    if driver == "coretemp" and name.startswith("Package id")
                    else "nvme" if driver == "nvme" and name == "Composite" else None
                )
                if kind:
                    value = (
                        float(
                            label.with_name(
                                label.name.replace("_label", "_input")
                            ).read_text()
                        )
                        / 1000
                    )
                    if not math.isfinite(value) or not 0 < value < 125:
                        raise ValueError("INVALID_SENSOR")
                    readings[kind].append(value)
                    identities.append(
                        dict(
                            device=str((device / "device").resolve()),
                            driver=driver,
                            label=name,
                            value=value,
                        )
                    )
        except (OSError, ValueError):
            return dict(cpu=None, nvme=None, identities=identities)
    return dict(
        cpu=max(readings["cpu"], default=None),
        nvme=max(readings["nvme"], default=None),
        identities=identities,
    )


def resources(directory):
    data = sensors()
    memory = dict(
        line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()
    )
    artifact_bytes = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                artifact_bytes += path.stat().st_size
        except FileNotFoundError:
            # A worker atomically renamed its temporary checkpoint during scan.
            continue
    data.update(
        ram_gib=int(memory["MemAvailable"].split()[0]) * 1024 / GIB,
        free_gib=shutil.disk_usage(directory).free / GIB,
        artifact_gib=artifact_bytes / GIB,
    )
    return data


def pause_reasons(data, limits):
    reasons = []
    for name in ("cpu", "nvme"):
        if data[name] is None:
            reasons.append(f"{name}:SENSOR_UNAVAILABLE")
        elif data[name] >= limits[name]:
            reasons.append(f"{name}:TEMPERATURE")
    if data["ram_gib"] < limits["ram_gib"]:
        reasons.append("RAM")
    if data["free_gib"] < limits["free_gib"]:
        reasons.append("DISK")
    if data["artifact_gib"] > limits["artifact_gib"]:
        reasons.append("ARTIFACT_BUDGET")
    return reasons


def tone(path):
    rate = 24000
    samples = []
    for hz, seconds in ((740, 0.22), (0, 0.06), (920, 0.28), (0, 0.04)):
        for i in range(round(rate * seconds)):
            envelope = min(1, i / (rate * 0.008), (rate * seconds - i) / (rate * 0.008))
            samples.append(
                round(5500 * envelope * math.sin(2 * math.pi * hz * i / rate))
                if hz
                else 0
            )
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def play(path, failures=None):
    for binary in ("paplay", "pw-play", "aplay", "ffplay"):
        executable = shutil.which(binary)
        if executable:
            args = [executable, str(path)]
            if binary == "ffplay":
                args = [
                    executable,
                    "-nodisp",
                    "-autoexit",
                    "-loglevel",
                    "quiet",
                    str(path),
                ]
            try:
                result = subprocess.run(
                    args,
                    timeout=3,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode == 0:
                    return True
                if failures is not None:
                    failures.append(
                        dict(
                            player=binary,
                            returncode=result.returncode,
                            stderr=(result.stderr or "")[:240],
                        )
                    )
            except (subprocess.SubprocessError, OSError) as error:
                if failures is not None:
                    failures.append(dict(player=binary, error=str(error)[:240]))
    if failures is not None and not failures:
        failures.append(dict(error="NO_SUPPORTED_AUDIO_PLAYER"))
    return False


def alarm(directory, kind, detail):
    prior = read(directory / "alarm.json", {})
    previous_ack = read(directory / "ack.json", {})
    # Deduplicate an active incident, but NEVER reuse an acknowledged incident
    # when the same fault happens again during a later run or resumed stage.
    if (
        prior.get("kind") == kind
        and prior.get("detail") == detail
        and previous_ack.get("incident") != prior.get("incident")
    ):
        return prior
    key = hashlib.sha256(
        json.dumps([kind, detail, time.time_ns()], sort_keys=True).encode()
    ).hexdigest()
    value = dict(incident=key, kind=kind, detail=detail, created=time.time())
    write(directory / "alarm.json", value)
    event(directory, "ALARM", alarm=value)
    if shutil.which("notify-send") and (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        try:
            subprocess.run(
                ["notify-send", "Finsport FS-021", kind],
                check=False,
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError) as error:
            event(directory, "NOTIFICATION_UNAVAILABLE", reason=str(error)[:200])
    return value


def ack(directory):
    value = read(directory / "alarm.json")
    if not value:
        raise ValueError("NO_ALARM_TO_ACK")
    write(directory / "ack.json", dict(incident=value["incident"], time=time.time()))
    event(directory, "ACK", incident=value["incident"])


def sound_pending(directory, wav):
    value = read(directory / "alarm.json", {})
    if value and read(directory / "ack.json", {}).get("incident") != value["incident"]:
        failures = []
        if not play(wav, failures=failures):
            prior = read(directory / "audio_failure.json", {})
            if prior.get("incident") != value["incident"]:
                details = dict(
                    incident=value["incident"],
                    attempts=failures,
                    detected_at=time.time(),
                )
                write(directory / "audio_failure.json", details)
                event(directory, "AUDIO_UNAVAILABLE", **details)
                print(
                    f'ALARM {value["kind"]} | audio unavailable: {failures} '
                    "| ACK from another terminal",
                    flush=True,
                )
        return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--ack-alarm", action="store_true")
    parser.add_argument("--sound-test", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--cpu", type=float, default=80)
    parser.add_argument("--nvme", type=float, default=70)
    parser.add_argument("--ram-gib", type=float, default=4)
    parser.add_argument("--free-gib", type=float, default=80)
    parser.add_argument("--artifact-gib", type=float, default=50)
    parser.add_argument("--heartbeat-timeout", type=float, default=60)
    parser.add_argument("--shutdown-grace", type=float, default=60)
    options, command = parser.parse_known_args(argv)
    directory = options.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if options.ack_alarm:
        ack(directory)
        return 0
    if command and command[0] == "--":
        command = command[1:]
    limits = {
        key: getattr(options, key)
        for key in ("cpu", "nvme", "ram_gib", "free_gib", "artifact_gib")
    }
    import fcntl

    with (directory / "supervisor.lock").open("a") as mutex:
        fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix="fs021-audio-") as temporary:
            wav = Path(temporary) / "alarm.wav"
            tone(wav)
            if options.sound_test:
                alarm(
                    directory,
                    "MANUAL_SOUND_TEST",
                    dict(nonce=time.time(), bounded_seconds=20),
                )
                deadline = time.monotonic() + 20
                try:
                    while time.monotonic() < deadline:
                        if not sound_pending(directory, wav):
                            break
                        time.sleep(4)
                except KeyboardInterrupt:
                    print("\nFS021_SOUND_TEST_CANCELLED", flush=True)
                    return 130
                return 0
            reason = None
            previous = read(directory / "supervisor.json", {})
            if (
                previous.get("status")
                in {"RUNNING", "PAUSE_RESOURCE", "STOP_TECHNICAL"}
                and not options.resume
            ):
                alarm(
                    directory,
                    "STOP_TECHNICAL",
                    "INCOMPLETE_EXECUTION_EXPLICIT_RESUME_REQUIRED",
                )
                command = []
                reason = "STOP_TECHNICAL"
            if options.resume:
                # Hysteresis: sustained lower temperatures before explicit restart.
                cool_since = None
                for _ in range(16):
                    data = resources(directory)
                    cool = (
                        not pause_reasons(data, limits)
                        and data["cpu"] <= 70
                        and data["nvme"] <= 60
                    )
                    cool_since = (cool_since or time.monotonic()) if cool else None
                    if cool_since is not None and time.monotonic() - cool_since >= 30:
                        break
                    time.sleep(3)
                if cool_since is None or time.monotonic() - cool_since < 30:
                    alarm(directory, "PAUSE_RESOURCE", "HYSTERESIS_NOT_SATISFIED")
                    reason = "PAUSE_RESOURCE"
                    command = []
            worker = None
            started = time.time()
            data = resources(directory)
            failures = pause_reasons(data, limits)
            if failures:
                reason = "PAUSE_RESOURCE"
                alarm(directory, reason, failures)
                command = []
            if reason is not None:
                write(
                    directory / "supervisor.json", dict(status=reason, time=time.time())
                )
            write(
                directory / "control.json",
                dict(time=time.time(), pause=reason is not None),
            )
            if command:
                # Isolate the worker's process group, so an explicit emergency
                # shutdown does not signal the shell or the operational stack.
                worker = subprocess.Popen(command, start_new_session=True)
                event(
                    directory,
                    "STAGE_START",
                    command=command,
                    pid=worker.pid,
                    resources=data,
                    limits=limits,
                )
                write(
                    directory / "supervisor.json",
                    dict(status="RUNNING", pid=worker.pid, started=started),
                )
            frozen = read(directory / "spec.json", {})
            candidates = frozen.get("input", {}).get("candidates", [])
            last_checkpoint = None
            last_snapshot = 0

            shutdown_signal = None
            shutdown_since = None
            forced = False

            def request_pause(signum, *_):
                nonlocal reason, shutdown_signal, shutdown_since, forced
                if shutdown_signal is None:
                    shutdown_signal = signum
                    shutdown_since = time.monotonic()
                    if worker is not None and worker.poll() is None:
                        reason = "PAUSE_RESOURCE"
                        alarm(directory, reason, "USER_INTERRUPT_CHECKPOINT_THEN_PAUSE")
                    # Without a running worker (e.g. completed or preflight
                    # paused), do not block SIGTERM/Ctrl+C on alarm ACK.
                elif worker is not None and worker.poll() is None:
                    forced = True
                    reason = "STOP_TECHNICAL"
                    alarm(directory, reason, "SECOND_INTERRUPT_WORKER_TERMINATION")

            signal.signal(signal.SIGINT, request_pause)
            signal.signal(signal.SIGTERM, request_pause)
            while True:
                if shutdown_signal is not None and worker is None:
                    event(
                        directory,
                        "OPERATOR_STOP",
                        status=reason,
                        signal=int(shutdown_signal),
                    )
                    return 130 if shutdown_signal == signal.SIGINT else 143
                if (
                    worker is not None
                    and worker.poll() is None
                    and shutdown_signal is not None
                ):
                    if (
                        forced
                        or time.monotonic() - shutdown_since >= options.shutdown_grace
                    ):
                        reason = "STOP_TECHNICAL"
                        alarm(directory, reason, "OPERATOR_STOP_WORKER_GRACE_EXPIRED")
                        event(directory, "WORKER_TERMINATION_REQUEST", pid=worker.pid)
                        try:
                            os.killpg(worker.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        # Only an explicit operator stop uses process termination;
                        # ordinary resource pauses remain cooperative/checkpointed.
                        try:
                            worker.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            try:
                                os.killpg(worker.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                if shutdown_signal is not None and worker is None:
                    event(directory, "OPERATOR_STOP", status=reason)
                    return 130 if shutdown_signal == signal.SIGINT else 143
                data = resources(directory)
                failures = pause_reasons(data, limits)
                heartbeat = read(directory / "heartbeat.json", {})
                if worker and worker.poll() is None:
                    if failures and reason is None:
                        reason = "PAUSE_RESOURCE"
                        alarm(directory, reason, failures)
                    if (
                        time.time() - max(started, heartbeat.get("time", 0))
                        > options.heartbeat_timeout
                        and reason is None
                    ):
                        reason = "STOP_TECHNICAL"
                        alarm(directory, reason, "HEARTBEAT_EXPIRED")
                    write(
                        directory / "control.json",
                        dict(time=time.time(), pause=reason is not None),
                    )
                elif worker is not None:
                    status = read(directory / "worker.json", {})
                    reason = reason or (
                        status.get("status")
                        if worker.returncode == 0
                        else "STOP_TECHNICAL"
                    )
                    if reason not in {
                        "OBSERVED_COMPLETE",
                        "COMPLETE",
                        "PAUSE_RESOURCE",
                    }:
                        reason = "STOP_TECHNICAL"
                    write(
                        directory / "supervisor.json",
                        dict(
                            status=reason,
                            returncode=worker.returncode,
                            time=time.time(),
                        ),
                    )
                    event(
                        directory,
                        "STAGE_END",
                        status=reason,
                        returncode=worker.returncode,
                    )
                    prior_alarm = read(directory / "alarm.json", {})
                    if reason != "OBSERVED_COMPLETE" and not (
                        prior_alarm.get("kind") == reason
                        and prior_alarm.get("created", 0) >= started
                    ):
                        alarm(
                            directory,
                            reason,
                            status or dict(returncode=worker.returncode),
                        )
                    worker = None
                child_progress = [
                    read(p, {}) for p in (directory / "compute").glob("*.json")
                ]
                live = [
                    p for p in child_progress if time.time() - p.get("time", 0) < 15
                ]
                current = (
                    max(live, key=lambda p: p.get("time", 0)) if live else heartbeat
                )
                candidate_index = current.get("candidate")
                composition = "?"
                if isinstance(candidate_index, int) and 0 <= candidate_index < len(
                    candidates
                ):
                    arm = candidates[candidate_index]
                    pd = arm["prediction_decision"]
                    composition = f'{pd["prediction_code"]} × {pd["decision_policy"]}({pd["decision_variant"]}) × {arm["capital"]["code"]}'
                checkpoint = heartbeat.get("last_checkpoint")
                if checkpoint and checkpoint != last_checkpoint:
                    event(directory, "CHECKPOINT", checkpoint=checkpoint)
                    last_checkpoint = checkpoint
                if sys.stdout.isatty() or time.time() - last_snapshot >= 30:
                    text = f'{heartbeat.get("stage", "MONITOR")} {heartbeat.get("completed", 0)}/{heartbeat.get("total", "?")} | candidate={candidate_index} {composition} | lag={heartbeat.get("lag")} L={heartbeat.get("block_length")} | workers={heartbeat.get("workers", 0)} | last={current.get("last_termination", heartbeat.get("last_termination"))} | checkpoint={checkpoint} | CPU={data["cpu"]}C NVMe={data["nvme"]}C free={data["free_gib"]:.1f}GiB'
                    print(
                        ("\r\033[K" if sys.stdout.isatty() else "") + text,
                        end="" if sys.stdout.isatty() else "\n",
                        flush=True,
                    )
                    last_snapshot = time.time()
                pending = sound_pending(directory, wav)
                if worker is None and not pending:
                    if sys.stdout.isatty():
                        print()
                    return 0 if reason in {"COMPLETE", "OBSERVED_COMPLETE"} else 2
                time.sleep(4)


if __name__ == "__main__":
    raise SystemExit(main())
