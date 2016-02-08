#!/usr/bin/env bash

qconf -sc \
    | awk ' /^[^#]/ { print $1 " " $4 " " $3 } '

# Example output of qconf -sc

# #name                      shortcut                   type       relop   requestable consumable default  urgency 
# #----------------------------------------------------------------------------------------------------------------
# aa_mcad                    aa_mcad                    INT        <=      YES         YES        0        0
# aa_r_cfd                   aa_r_cfd                   INT        <=      YES         JOB        0        0
# aa_r_hpc                   aa_r_hpc                   INT        <=      YES         JOB        0        0
# arbbl                      arbbl                      INT        <=      YES         YES        0        0
# arch                       a                          STRING     ==      YES         NO         NONE     0
# batch                      bat                        BOOL       ==      YES         NO         0        0
# zex                        zex                        BOOL       EXCL    YES         YES        false    0
# # >#< starts a comment but comments are not saved across edits --------
