#!/usr/bin/env bash

dest_file=/etc/icinga2/conf.d/sge-services.conf

if [ ! -w "$dest_file" -o ! -e "$dest_file" ]; then
    echo "Warning: cannot write to $dest_file or it does not exist: writing to a temporary file instead" >&2
    tmp_file=`mktemp -p /tmp sge-services.conf.tmp.XXXXXXXXXXXXXX`
    echo " Temporary file: $tmp_file" >&2
    dest_file="$tmp_file"
fi

:>$dest_file

for check_name in `\
    ./per-host-thresholds.yaml.sh \
        | grep -o '^  [^:]*' \
        | sort -u ` 
    do
        if [ "$check_name" != "qname" ]; then
            echo "
apply Service \"$check_name\" {
  import \"generic-service\"
  check_command = \"passive\"

  assign where host.vars.uses_$check_name == \"1\"
} " >>$dest_file
        fi
done

echo "Done. If you changed the file in-place, remember to restart Icinga2." >&2

