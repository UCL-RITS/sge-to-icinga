#!/usr/bin/env bash


sensor_searches="$( qconf -sc \
                     | grep -o '^[^ ]*_nagtxt' \
                     | cut -f 1 -d_ \
                     | sed -e 's/^/l:/' \
                     | sed -e 'p;s/\$/_nagtxt/p' \
                  )" 

extra_searches="$(echo -e '\nerror\n@\n')"

grep_searches="${sensor_searches}${extra_searches}"

./per-host-thresholds.yaml.sh \
    | grep qname \
    | sed -e 's/  qname: //' \
    | tr '\n' ',' \
    | xargs -Iqueues qstat -explain a -F -q queues \
    | grep -F "$grep_searches"\
    | sed \
      -e 's/^\t[a-z][a-z]:/\t/' \
      -e 's/^\talarm [a-z][a-z]:/\talarm /' \
      -e 's/^\([A-Za-z]*\)@\([A-Za-z0-9-]*\)[ \.].*lx-amd64[ ]*\([uaACsSdDecoP]*\)$/---\n  hostname: \2\n  qname: \1\n  qstate: \3/' \
      -e 's/^\([A-Za-z]*\)@\([A-Za-z0-9-]*\)[ \.].*-NA-[ ]*-NA-[ ]*\([uaACsSdDecoP]*\)$/---\n  hostname: \2\n  qname: \1\n  qstate: \3/' \
      -e 's/\t\([a-z_]*\)=\([0-9.-]*\)$/  \1: \2/' \
      -e 's/\t\([a-z_]*\)=\([^ :]*\)$/  \1: \2/' \
      -e 's/\t\([a-z_]*\)=\(.*\)$/  \1: "\2"/' \
    | sed -e 's/^  qstate: $/  qstate: y/' \
    | awk 'BEGIN { 
               error_buffer = "" 
               alarm_buffer = ""
           }
           /^-/ {
               if (error_buffer != "") {
                   printf "  errors:\n%s", error_buffer
                   error_buffer = ""
               }
               if (alarm_buffer != "") {
                   printf "  alarms:\n%s", alarm_buffer
                   alarm_buffer = ""
               }
           }
           /^\talarm/ {
               # default length of substr is 1, so we use 10000 to get whole remaining string
               alarm_buffer = sprintf("%s    - \"%s\"\n", alarm_buffer, substr($0, 8, 10000))
           } 
           /^\terror/ {
               gsub("\"", "\\\"", $0)
               error_buffer = sprintf("%s    - \"%s\"\n", error_buffer, substr($0, 9, 10000)) 
           }
           /^[^\t]/ {
               print $0
           }
           END {
               printf "  errors:\n%s", error_buffer
               printf "  alarms:\n%s", alarm_buffer
           }
           ' 


# Possible queue states:
#  * u(nknown)
#  * a(larm)
#  * A(larm)
#  * C(alendar suspended)
#  * s(uspended)
#  * S(ubordinate)
#  * d(isabled)
#  * D(isabled)
#  * E(rror)
#  * c(configuration ambiguous)
#  * o(rphaned)
#  * P(reempted)

#  * y(es, everything is fine) -> added by me
