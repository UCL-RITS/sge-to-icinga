# SGE to Icinga2 Daemon

This bundle takes resource information from SGE and puts it into Icinga2, creating hosts where necessary.

#### Dependencies

* Python 2.7
* bash, sed, gawk, grep, sort
* SGE client binaries (`qhost`, `qstat`, `qconf`) + config
* An Icinga2 server with NSCA configured to accept passive checks
* A compatible version of `send_nsca` (it seems to have compatibility issues between versions)

##### Python Modules

* daemon (python-daemon on PyPi, *not* daemon on PyPi)
* Requests
* yaml (PyYaml on PyPi)

#### Useful Docs

* [Main Icinga2 Docs](http://docs.icinga.org/icinga2/snapshot/doc/module/icinga2/toc)
* [Setting up Icinga2 with NSCA](https://wiki.icinga.org/pages/viewpage.action?pageId=23887907)


#### To make NSCA work

 * change the command pipe to the Icinga2 one -- the default is classic Nagios
 * this setting is in `/etc/nagios/nsca.cfg`, the Icinga2 value is `command_file=/var/run/icinga2/cmd/icinga2.cmd`
 * make sure the encryption algo and password in the `send_nsca.cfg` and `nsca.cfg` files match
 * set NSCA to aggregate writes
 * ensure permissions allow NSCA to write to the command pipe -- I attempted to do this by setting it 777, but that didn't seem to work, so I set NSCA to run as the Icinga user instead. *shrug*
