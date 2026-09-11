# Finsport — FS-014 concurrent runtime / isolated development / storage & backup research

**Status:** FINAL
**Artifact class:** REFERENCE ONLY
**Project:** Finsport
**Planning identity:** FS-014
**Date:** 2026-09-09
**Research mode:** local evidence + targeted architecture synthesis
**Deep Research:** NOT USED
**Provider calls:** NONE
**Implementation performed:** NONE

---

# 1. Executive summary

FS-014 is ready for ticket definition.

Primary operational problem:

```text
current development workflow
→ make dev-up
→ automatic operational acquisition is not running

therefore

frequent development
→ interrupts prospective evidence accumulation
```

The approved direction is:

```text
one stable operational stack
+
one isolated ephemeral development stack
```

using the same Git repository but different runtime identities.

Operational:

```text
Compose project
→ finsport

code
→ immutable image built from deployed stable master

PostgreSQL
→ existing finsport_postgres_data

Redis
→ operational

Celery Beat
→ YES

providers
→ YES

lifecycle
→ may remain running while development occurs
```

Development:

```text
Compose project
→ finsport-dev

code
→ current ticket branch

PostgreSQL
→ isolated clone of operational DB

Redis
→ isolated

Celery Beat
→ NO

automatic providers
→ NO

lifecycle
→ ephemeral
→ destroyed completely at ticket close
```

The current operational PostgreSQL database is irreplaceable research evidence.

Hard invariant:

```text
finsport_postgres_data
→ NEVER DELETE
```

FS-014 also absorbs the separate Backup/restore backlog concern with a deliberately simple contract:

```text
one rolling validated backup
→ latest.dump

weekly
→ Monday 20:00 America/Lima

pre-deploy
→ refresh same backup

restore drill
→ isolated target only
```

Storage investigation shows no partition operation is currently justified.

Observed root:

```text
~407 GiB total
~93 GiB free before cleanup
```

Observed Docker:

```text
/var/lib/docker
→ ~223 GiB

build cache
→ ~196.9 GB total
→ ~122.2 GB reclaimable

images
→ ~97.2 GB total
→ ~56.7 GB reclaimable
```

Operational Finsport DB:

```text
~153 MB
```

Therefore:

```text
partition resize
→ NOT REQUIRED

first solution
→ one-time safe host cleanup
→ bounded BuildKit GC thereafter
```

The global host cleanup occurs only once in FS-014.

Future tickets clean only their own `finsport-dev` resources at the END of the ticket.

---

# 2. Accepted inputs

Local baselines:

```text
FS-014_storage_concurrent_runtime_baseline.txt
FS-014_storage_runtime_final_baseline.txt
```

FS-013 operational handoff is an accepted prerequisite because FS-014 must preserve the new continuously accumulating prospective evidence lifecycle.

Relevant final FS-013 facts carried forward:

```text
MARKET_CONSENSUS v2
→ operational automatically

capture
→ T-6h / T-60m / T-30m

scheduler owner
→ Celery Beat / football.pipeline.wake

future calibration
→ depends on prospective evidence accumulation
```

FS-014 must make continued development compatible with that normal automatic operation.

---

# 3. Local storage findings

Observed Ubuntu root:

```text
filesystem
→ /dev/nvme1n1p3
→ ext4

size
→ ~407 GiB

used
→ ~294 GiB

available
→ ~93 GiB
```

Observed `/var`:

```text
/var
→ ~233 GiB

/var/lib
→ ~231 GiB

/var/lib/docker
→ ~223 GiB
```

Other host consumers are comparatively small:

```text
/var/lib/snapd
→ ~7.4 GiB

~/.cache
→ ~4.6 GiB

APT archive cache
→ ~363 MiB

systemd journal
→ ~561 MiB
```

The main storage problem is Docker build/image accumulation, not Finsport PostgreSQL.

---

# 4. Docker storage findings

Observed:

```text
Images
→ ~97.21 GB
→ ~56.72 GB reclaimable

Local Volumes
→ ~6.68 GB

Build Cache
→ ~196.9 GB
→ ~122.2 GB reclaimable
```

The operational Finsport PostgreSQL named volume exists as:

```text
finsport_postgres_data
```

and must never be subject to broad volume pruning.

Approved storage approach:

```text
FS-014
→ one-time safe global cleanup

after FS-014
→ BuildKit GC bounded permanently
→ future global cleanup manual only
```

No global cleanup becomes part of every development ticket.

Preferred BuildKit GC target:

```text
enabled
defaultKeepStorage
→ 30GB
```

This is a project/host operational decision intended to prevent return to ~200 GB of build cache.

---

# 5. Partition boundary

Two NVMe devices contain existing Microsoft/NTFS partitions.

No partition resize is justified by current evidence.

FS-014 must not perform:

```text
fdisk writes
parted resize
ntfsresize
mkfs
partition deletion
```

If safe cleanup still leaves materially inadequate headroom, FS-014 stops and returns to the main chat before any partition decision.

---

# 6. Current runtime defect

Current Compose uses:

```text
name: finsport
```

and application services bind-mount:

```text
.:/app
```

including Django/Celery/Beat paths.

Therefore:

```text
working tree changes
→ can become visible to running operational app containers
```

This prevents safe simultaneous:

```text
stable operation
+
branch development
```

The fix is not a second repository.

The fix is runtime immutability for the operational stack.

---

# 7. Final topology

## Operational

```text
project
→ finsport

source
→ immutable image built from deployed stable master

source bind mount
→ NO

PostgreSQL
→ existing durable operational DB

Redis
→ operational

Beat
→ YES

automatic provider work
→ YES

observability
→ YES

lifecycle
→ stable / long-running
```

The operational project identity remains `finsport` specifically to preserve existing durable volume identities.

## Development

```text
project
→ finsport-dev

source
→ current Git branch

source bind mount
→ YES

PostgreSQL
→ isolated cloned DB

Redis
→ isolated

Beat
→ NO

automatic provider work
→ NO

ports
→ isolated

lifecycle
→ disposable
```

Only one development stack is required at a time.

---

# 8. Development DB bootstrap

The development DB should start from a recent consistent snapshot of the operational DB.

Conceptual flow:

```text
operational PostgreSQL remains running
↓
pg_dump
↓
isolated finsport-dev PostgreSQL
↓
pg_restore
↓
branch migrations
↓
dev services
```

Operational and dev databases must never share a writable PostgreSQL volume.

Development migrations/tests may freely mutate the dev DB.

They must not write to operational PostgreSQL.

---

# 9. Future ticket lifecycle

FS-014 itself is executed under the existing F009 lifecycle.

After FS-014 closes, future tickets use the simplified lifecycle below.

## Start

The previous ticket is responsible for leaving no development residue.

Therefore normal ticket start assumes:

```text
operational finsport
→ running latest deployed master

finsport-dev
→ absent
```

Normal start:

```text
sync master
→ create ticket branch
→ make dev-create
```

`make dev-create` creates the isolated dev stack and clones the operational DB.

If unexpected `finsport-dev` resources exist, fail closed instead of silently cleaning them.

No routine `dev-clean` occurs at the start.

## End

Cleanup belongs at the end:

```text
make dev-destroy
```

This removes only development resources.

Then, after merge:

```text
sync master
→ local deploy
→ operational latest master running
```

The next ticket therefore does not need residue archaeology.

---

# 10. Local deployment

A second Git repository/worktree is unnecessary.

Operational containers continue running an immutable image from the previously deployed stable master even while the working tree is on a feature branch.

After merge:

```text
destroy dev
↓
git switch master
git pull --ff-only
↓
refresh validated rolling backup
↓
build current master operational image
↓
controlled operational safe-down
↓
apply migrations/deploy
↓
make up
↓
status/health validation
```

A short bounded deployment interruption is acceptable.

Development itself should not interrupt prospective operation.

Exact Makefile/Compose/script arrangement belongs to implementation preflight.

---

# 11. Development cleanup contract

At ticket close, all resources owned by `finsport-dev` must be removed:

```text
containers
network
PostgreSQL volume
Redis volume
other dev named volumes
temporary clone/dump artifacts
ticket-local runtime residue
```

Operational resources must remain untouched.

Hard distinction:

```text
global host cleanup
→ one time in FS-014 only

per-ticket cleanup
→ finsport-dev only
→ at ticket END
```

---

# 12. Backup / restore contract

The existing separate Backup/restore backlog concern is absorbed by FS-014.

## Rolling backup

Maintain one normal backup:

```text
latest.dump
```

No historical generation accumulation.

## Schedule

```text
Monday
20:00
America/Lima
```

Rationale:

```text
machine more likely to be running
+
evening operational preference
```

This is a project scheduling decision, not a universal football-density theorem.

## Replacement safety

```text
pg_dump
→ latest.dump.tmp

validate
→ atomic replace latest.dump

failure
→ previous latest.dump remains intact
```

## Pre-deploy

Every operational deploy refreshes the same rolling backup before migrations/runtime replacement.

No second backup generation is created.

## Restore drill

FS-014 must prove:

```text
latest.dump
→ restore into isolated scratch/dev PostgreSQL
→ basic DB/schema smoke succeeds
→ scratch target destroyed
```

Restore testing must never target operational PostgreSQL.

---

# 13. Process simplification

FS-014 must not make F009 more ceremonial.

After FS-014, durable process sources should be updated by replacing obsolete instructions rather than appending redundant layers.

Expected simplified normal lifecycle:

```text
START
→ sync master
→ create branch
→ make dev-create

DEVELOP
→ existing bounded F009 implementation/review/UAT

END
→ merge
→ make dev-destroy
→ sync master
→ make deploy-local
```

Avoid repeated manual ceremony around:

```text
git status
branch identity
commit SHA
remote archaeology
already-proven runtime state
duplicate full checks
```

Safety validation should preferably live inside deterministic commands and fail closed.

---

# 14. Durable-source update boundary

Do not update F003/F004/F006/F009 during FS-014 implementation before technical close.

After FS-014 closes, the main chat performs one durable-source update incorporating lessons from both FS-013 and FS-014.

Expected projection:

```text
F003
→ stable operational image + isolated dev architecture

F004
→ runtime/deploy/backup/storage operating contract

F006
→ FS-013/FS-014 status
→ Backup/restore standalone backlog item removed/resolved

F009
→ simplified dev-create/dev-destroy/local-deploy lifecycle
→ remove obsolete ceremony
```

Do not increase F009 unnecessarily.

F000 responsibility mapping is not expected to change.

---

# 15. Ticket readiness

```text
RESEARCH STATUS
→ COMPLETE ENOUGH FOR TICKET

TICKET READINESS
→ READY_FOR_TICKET

PARTITION CHANGE
→ NOT REQUIRED

OPERATIONAL DB REPLACEMENT
→ FORBIDDEN

GLOBAL CLEANUP
→ ONE TIME IN FS-014

FUTURE PER-TICKET CLEANUP
→ DEV STACK ONLY / END OF TICKET

BACKUP/RESTORE
→ ABSORB INTO FS-014
```

**STOP — NEXT: F008 ticket/package.**
