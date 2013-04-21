secret-robot
============

Python interactive shell for controlling RackSpace Cloud Servers (and hopefully DNS settings).

The following are desired commands. Some of these are currently implemeneted as Bash scripts.

* apache add site %s = Add new Apache vhost under /var/www/vhost/%s.
* apache remove site %s = Delete Apache vhost under /var/www/vhost/%s.
* apache restart|stop|start
* mysql add db %s = Add new MySQL database named %s.
* mysql remove db %s = Delete MySQL database named %s.
* mysql add user %s = Add new MySQL user named %s.
* mysql remove user %s = Delete MySQL user named %s.
* mysql add super %u %d = Give MySQL user named %u all privilieges on database named %d.
* mysql remove super %u %d = Revoke all priviliges from MySQL user named $u on database named $d.
* mysql restart|stop|start
* add lamp vhost %s %u %d = apache add site %s && mysql add db %d && mysql add user %u && mysql add super %u %d.
* remove lamp vhost %s = apache remove site %s && mysql remove super %u %d && mysql remove user %u && mysql remove db %d
* add dns %s = rackspace dns add cname record pointing %s to this server's IP.
* autoadd lamp vhost %s = apache add site %s && mysql add db %s && mysql add user %s && mysql add super %s %s && add subdomain %s.
* autoremove lamp vhost %s = apache remove site %s && mysql remove super %s %s && mysql remove user %s && mysql remove db %s
* chapache %s = Change owner and group of current directory and all underneath to apache-user:apache-group.
* update = apt-get update
* upgrade = apt-get upgrade
* info = free -m && ps && who && last
* install %s = apt-get install %s
* uninstall %s = apt-get uninstall %s
* restart|reboot
* lamp restart|reboot
* add github-webhook %l %r = Add a GitHub webook listener script at %l to update repository at %r.
* add wordpress
* remove wordpress
* add wordpress-install-template
* autoadd wordpress-install-template %s

The CLI will need to have directory navigation with the standard unix system (cd, ., .., pwd, etc.) and many commands will act directly in the current directory.
