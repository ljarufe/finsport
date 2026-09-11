# Backup And Local Deployment

Finsport keeps exactly one normal rolling PostgreSQL backup outside Git and
Docker volumes:

```text
~/.local/share/finsport/backups/latest.dump
```

`make backup` identifies exactly the running `finsport/db` container, verifies
its PostgreSQL 17 identity and the `finsport_postgres_data` mount, writes a
mode-0600 temporary sibling, validates it with `pg_restore --list`, and replaces
`latest.dump` atomically. The directory is forced to mode 0700. A failure before
replacement leaves the previous backup intact.

Run the isolated restore drill with:

```bash
make backup-verify
```

The drill refuses a stale scratch container, restores only into a uniquely
named PostgreSQL 17 container backed by tmpfs, checks the Django migration table
and public schema, and removes the scratch container on success or failure. It
never mounts or connects to the operational PostgreSQL volume.

## Weekly User Timer

The scheduled job must execute a stable installed copy, not the mutable ticket
checkout. Install or update the repository-owned artifacts as the normal user:

```bash
install -D -m 0755 tools/finsport_backup.py \
  "$HOME/.local/libexec/finsport/finsport-backup"
install -D -m 0644 operations/systemd/finsport-backup.service \
  "$HOME/.config/systemd/user/finsport-backup.service"
install -D -m 0644 operations/systemd/finsport-backup.timer \
  "$HOME/.config/systemd/user/finsport-backup.timer"
systemctl --user daemon-reload
systemctl --user enable --now finsport-backup.timer
systemctl --user list-timers finsport-backup.timer
```

The timer runs Monday at 20:00 in `America/Lima` and uses no Celery scheduler.
Installation and activation are operator-owned host actions; repository commands
do not perform them.

To remove the schedule, disable it before removing the two installed unit files:

```bash
systemctl --user disable --now finsport-backup.timer
```

## Local Deploy

After a ticket is merged, destroy its development environment, synchronize local
`master`, and deploy:

```bash
make dev-destroy
git switch master
git pull --ff-only
make deploy-local
```

`make deploy-local` refuses any branch other than clean `master`. It refreshes
the rolling backup before building the application and repository-configured
Nginx/observability images. It then uses the existing safe operational drain,
starts the existing PostgreSQL and Redis volumes, applies migrations with the
new image, starts the operational and observability profiles, and reports
status. It never uses `down -v`, recreates the operational database, or fetches
Git history/remotes.
