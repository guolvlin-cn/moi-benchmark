#!/bin/zsh
set -Eeuo pipefail

MYSQL=(/opt/homebrew/opt/mysql-client/bin/mysql --protocol=tcp -h127.0.0.1 -P6001 -uroot -p111)

# Smallest first keeps feedback frequent and avoids concurrent IVFFLAT builds
# exceeding the local MatrixOne container's 8 GiB memory limit.
targets=(
  'moi_stage1_ragas_wikieval|embedding_results'
  'moi_stage1_mmdocir_official|pages_bge_m3_vlm'
  'moi_stage1_mmdocir_official|layouts_bge_m3_vlm'
  'moi_stage1_docbench|embedding_results'
  'moi_stage1_mmdocir|embedding_results'
  'moi_stage1_mmdocrag|embedding_results'
)

for target in $targets; do
  db=${target%%|*}
  table=${target#*|}
  before=$(${MYSQL[@]} -Nse "SELECT COUNT(*) FROM \`$db\`.\`$table\`" 2>/dev/null)
  index_line=$(${MYSQL[@]} -Nse "SHOW INDEX FROM \`$db\`.\`$table\`" 2>/dev/null | python3 -c '
import sys
for line in sys.stdin:
    fields = line.rstrip("\n").split("\t")
    if len(fields) >= 14 and fields[4] == "embedding" and fields[10].lower() == "ivfflat":
        print(fields[2] + "|" + fields[13])
')
  if [[ -z "$index_line" ]]; then
    print -u2 "$(date '+%F %T') ERROR $db.$table has no IVFFLAT embedding index"
    exit 1
  fi
  old_index=${index_line%%|*}
  params=${index_line#*|}
  if [[ "$params" == *vector_l2_ops* ]]; then
    print "$(date '+%F %T') SKIP $db.$table rows=$before index=$old_index already_l2=1"
    continue
  fi
  if [[ "$params" != *vector_cosine_ops* ]]; then
    print -u2 "$(date '+%F %T') ERROR $db.$table unexpected index params: $params"
    exit 1
  fi

  new_index="idx_${table}_embedding_l2"
  print "$(date '+%F %T') START $db.$table rows=$before drop=$old_index create=$new_index"
  ${MYSQL[@]} "$db" -e "
    ALTER TABLE \`$table\` DROP INDEX \`$old_index\`;
    CREATE INDEX \`$new_index\`
      USING ivfflat ON \`$table\` (embedding)
      LISTS = 256 OP_TYPE 'vector_l2_ops';
  "

  after=$(${MYSQL[@]} -Nse "SELECT COUNT(*) FROM \`$db\`.\`$table\`" 2>/dev/null)
  if [[ "$after" -ne "$before" ]]; then
    print -u2 "$(date '+%F %T') ERROR $db.$table row count changed: before=$before after=$after"
    exit 1
  fi
  verified=$(${MYSQL[@]} -Nse "SHOW INDEX FROM \`$db\`.\`$table\`" 2>/dev/null | python3 -c '
import sys
name = sys.argv[1]
for line in sys.stdin:
    fields = line.rstrip("\n").split("\t")
    if len(fields) >= 14 and fields[2] == name and fields[10].lower() == "ivfflat" and "vector_l2_ops" in fields[13]:
        print(1)
' "$new_index")
  if [[ "$verified" != 1 ]]; then
    print -u2 "$(date '+%F %T') ERROR $db.$table L2 index verification failed"
    exit 1
  fi
  print "$(date '+%F %T') DONE $db.$table rows=$after index=$new_index op=vector_l2_ops"
done

print "$(date '+%F %T') ALL_DONE"
