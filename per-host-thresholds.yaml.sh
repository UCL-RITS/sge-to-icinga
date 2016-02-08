#!/usr/bin/env bash

# Turns the load thresholds output into per-host sections,
#  hyphen delimited per host, new-line delimited per value

#  * resolves multiple queue sets by most bits using awk --> more checks is best checks 

grep_search_terms="$(echo -e 'load_thresholds\nhostname\nqname')"

export SGE_SINGLE_LINE=1 

#qconf -sq \*@\* | grep -F "$grep_search_terms"

#exit

# NB: the first sed script here relies on the line order being:
# qname
# hostname
# load_thresholds

qconf -sq \*@\* \
    | grep -F "$grep_search_terms" \
    | sed -ne 'N
               s/^qname[ ]*\([A-Za-z]*\)\nhostname[ ]*\([A-Za-z0-9-]*\).*$/hostname=\2\nqname=\1@\2/mg
               N
               s/\n/ /g
               s/ [ ]*/ /
               s/load_thresholds [ ]*//
               p
               ' \
    | grep -v -F owner \
    | sort -u \
    | awk 'BEGIN { 
               old_hostname = ""; 
               line_buffer = ""; 
               line_buffer_components = 0;
           }  
           $1 != old_hostname {
              if ( line_buffer != "" ) {
                 print line_buffer;
              }
              line_buffer = $0
              line_buffer_components = split(line_buffer, dump_array, " ")
           }
           $1 == old_hostname { 
               this_components = split($0, dump_array, " ")
               if ( this_components > line_buffer_components) {
                   line_buffer = $0
                   line_buffer_components = this_components
               }
           } 
           {
               old_hostname = $1
           }
           END {
              print line_buffer
           }
          ' \
   | sed -e 's/hostname=\([^ ]*\)[ ]/- hostname: \1\n/'  \
         -e 's/\([^ ]\)$/\1 /' \
         -e 's/\([a-z_]*\)=\([0-9.]*\)[ ]/  \1: \2\n/g' \
         -e 's/\([a-z_]*\)=\([^ ]*\)[ ]/  \1: \2\n/g' \
   | sed '/^$/d'

# The last two lines there are for if it turns out strings need different handling
