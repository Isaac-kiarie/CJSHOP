#!/usr/bin/env bash
# Daily backup of the database and the uploaded media.
# The database password comes from ~/.cjshop-backup.cnf (mode 600), never from the command line.
set -euo pipefail
umask 077

DEST=/srv/cjshop/backups
KEEP_DAYS=14
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"

mysqldump --defaults-file="$HOME/.cjshop-backup.cnf" --single-transaction --no-tablespaces --triggers cjshop \
  | gzip -9 > "$DEST/db-$STAMP.sql.gz.part"
gzip -t "$DEST/db-$STAMP.sql.gz.part"                                   # the archive must be readable
test "$(stat -c %s "$DEST/db-$STAMP.sql.gz.part")" -gt 1000             # an empty dump is a failed dump
mv "$DEST/db-$STAMP.sql.gz.part" "$DEST/db-$STAMP.sql.gz"

tar -C /srv/cjshop/app -czf "$DEST/media-$STAMP.tar.gz" media

find "$DEST" -type f \( -name 'db-*.sql.gz' -o -name 'media-*.tar.gz' \) -mtime +"$KEEP_DAYS" -delete
echo "backup ok: $STAMP"