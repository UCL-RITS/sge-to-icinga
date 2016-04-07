import requests
import socket

class IcingaService:
    """ Intended to be the accessor for data about the Icinga service
    we need to update or send data to.
    """
    def __init__(self, config, logger):
        self.querier = IcingaServiceQuerier(config["icinga_server"],
                                            config["icinga_username"], 
                                            config["icinga_password"],
                                            logger, 
                                            verify_ssl=False)
        self.needs_update = True
        self.hostname_list = None
        self.update_host_list()
        self.logger = logger

    def add_host(self, host, add_vars=dict()):
        result = self.querier.create_host(host, add_vars)
        self.needs_update = True
        # maybe should only mark needs update if success? TODO
        return result

    def remove_host(self, host):
        self.needs_update = True
        self.querier.remove_host(host.name)
        pass

    def has_host(self, hostname):
        if self.needs_update == True:
            self.update_host_list()
        if hostname in self.hostname_list:
            return True
        else:
            return False

    def update_host_list(self):
        self.hostname_list = self.querier.get_hostname_list()
        self.needs_update = False

    def get_hostname_list(self):
        if self.needs_update == True:
            self.update_host_list()
        return self.hostname_list

    def ensure_hosts_exist(self, host_service_dict):
        for host in host_service_dict.keys():
            if not self.has_host(host):
                self.logger.warn("Icinga host entry \"%s\" was not found, attempting to create." % host)
                result = self.add_host(host, add_vars={ ("uses_%s" % x): "1" for x in host_service_dict[host] })
                if result == False:
                    self.logger.error("failed to add host entry for \"%s\"." % host)
                else:
                    self.logger.warn("Icinga host entry \"%s\" created." % host) 
                    # ^- this isn't really a warning but it closes off the warning above
            pass



class IcingaServiceQuerier:
    def __init__(self, base_url, username, password, logger, verify_ssl=True):
        self.logger = logger
        if base_url[-1] == "/":
            base_url = base_url[0:-1] 
            # ^-- trimming the url here makes our urls clearer below
        self.base_url = base_url
        self.verify_ssl = verify_ssl
        self.username = username
        self.password = password
        self.authenticated = False
        self.check_authentication()

    def __get(self, url_stub):
        return requests.get("%s/v1/%s" % (self.base_url, url_stub),
                            auth=(self.username, self.password), 
                            verify=self.verify_ssl)

    def __put(self, url_stub, data):
        return requests.put("%s/v1/%s" % (self.base_url, url_stub),
                            auth=(self.username, self.password),
                            data=data,
                            headers={ "Accept": "application/json" }, 
                            verify=self.verify_ssl)

    def __delete(self, url_stub):
        return requests.delete("%s/v1/%s" % (self.base_url, url_stub),
                            auth=(self.username, self.password), 
                            verify=self.verify_ssl)

    def check_authentication(self):
        response = self.__get("")

        if response.status_code == 200:
            self.authenticated = True
        else:
            self.authenticated = False
            error_msg = ''.join(["Auth check with Icinga server failed: ",
                                 "response code %d" % response.status_code])
            raise IcingaError(error_msg)
        return self.authenticated

    def delete_service(self, service_name):
        response = self.__get("objects/services?service=%s" % service_name)

        if response.status_code == 200:
            response = self.__delete("objects/services?service=%s" % hostname)
            if response.status_code != 200:
                error_msg = ("Could not delete service %s: code %d" % 
                             (hostname, response.status_code)
                             )
                raise IcingaError(error_msg)
        else:
            error_msg = ("Could not delete service %s: service not found." %
                         hostname
                         )
            raise IcingaError(error_msg)
        return
   
    def delete_host(self, hostname):
        response = self.__get("objects/hosts?host=%s" % hostname)
        
        if response.status_code == 200:
            response = self.__delete("objects/hosts?host=%s" % hostname)
            if response.status_code != 200:
                error_msg = ("Could not delete host %s: code %d" % 
                             (hostname, response.status_code)
                             )
                raise IcingaError(error_msg)
        else:
            error_msg = ("Could not delete host %s: host not found." %
                          hostname
                          )
            raise IcingaError(error_msg)
        return

    def remove_service_from_host(self, service_name, hostname):
        return self.delete_service("%s!%s" % (hostname, service_name))

    def create_template(self,template_name, template_content):
        pass

    def create_host(self, host, add_vars=dict()):
        response = self.__get("objects/hosts?host=%s" % host)

        if response.status_code == 200:
            raise IcingaError("tried to create host that already exists: %s" % host)
        else:
            try:
                host_ip=socket.gethostbyname(host)
            except socket.gaierror, e:                                                  
                self.logger.error('cannot resolve ip for host \"%s\" - assigning fake IP to host %s' % host)
                host_ip='none'
            add_vars_string = ', '.join([("\"%s\":\"%s\"" % (x, add_vars[x]))
                                          for x in add_vars.keys()])
            response = self.__put("objects/hosts/%s" % host, 
                    data = "{ \"templates\": [ \"generic-host\" ], \"attrs\": { \"address\": \"%s\", \"vars\": { \"sge_node\" : 1, %s } } }" % (host_ip, add_vars_string))
            if response.status_code == 200:
                return True
            else:
                self.logger.error(response.text)
                return False

    def create_service_as_clone(self, 
                                service_name, 
                                service_to_clone):
        pass

    def get_hosts(self):
        # curl -k -s -u 'username:password' 
        #   'https://localhost:5665/v1/objects/hosts?attrs=address'
        # pipe through `python -m json.tool` to prettyprint
        response = self.__get("objects/hosts")
        return response.json()

    def get_hostname_list(self):
        dict_hosts = self.get_hosts()
        return [ host["name"] for host in dict_hosts["results"] ]

    def get_all_services(self):
        # curl -k -s -u 'username:password'
        #   'https://localhost:5665/v1/objects/services'
        #  ^^ warn: this produces a *lot* of output
        response = self.__get("objects/services")
        return response.json()

    def update_service_list(self):
        pass
    
    # In Francesco's module there's another function called checkGroup but 
    #   I don't know what it does yet
    #    -> oh, it clones a hostgroup

class IcingaError(Exception):
    def __init__(self, value):
        self.value = value
        #TODO: push value also to log
        # e.g. when an exception is raised with "Could not get server info"
        #  make a logger message with: "Exception: Could not get server info"

    def __str__(self):
        return repr(self.value)
