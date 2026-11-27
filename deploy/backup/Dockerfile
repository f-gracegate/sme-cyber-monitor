# Backup and restore tooling: the matching PostgreSQL client plus GnuPG for encryption.
FROM postgres:17-alpine
RUN apk add --no-cache bash gnupg coreutils
COPY backup.sh restore.sh nightly.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/nightly.sh
USER postgres
ENTRYPOINT ["/bin/bash"]
