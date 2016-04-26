#!/usr/bin/env bash


sensor_searches="$( qconf -sc \
                     | grep -o '^[^ ]*_nagtxt' \
                     | cut -f 1 -d_ \
                     | sed -e 's/^/l:/' \
                     | sed -e 'p;s/\$/_nagtxt/p' \
                  )" 

extra_searches="$(echo -e '\nerror\nnode-\nglobal   \n')"

grep_searches="${sensor_searches}${extra_searches}"

qhost -F \
    | grep -F "$grep_searches"\
    | sed \
      -e 's/^global                  -               -    -    -    -     -       -       -       -       -$/---\n  hostname: global\n  uncontactable: "y"/' \
      -e 's/^\(node-....-...\)[ ]*lx-amd64[ ]*[0-9].*$/---\n  hostname: \1\n  uncontactable: "n"/' \
      -e 's/^\(node-....-...\)[ ]*-               -    -    -    -     -       -       -       -       -$/---\n  hostname: \1\n  uncontactable: "y"/' \
      -e 's/^[ ]*lx\-amd64.*$//' \
      -e 's/^   [a-z][a-z]:/   /' \
      -e 's/   \([a-z_]*\)=\([0-9.-]*\)$/  \1: \2/' \
      -e 's/   \([a-z_]*\)=\([^ :]*\)$/  \1: \2/' \
      -e 's/   \([a-z_]*\)=\(.*\)$/  \1: "\2"/' 

