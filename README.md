secret-robot
============

Python Fabric automation of common LAMP server tasks, currently focused on Debian on RackSpace Cloud Servers and using Cloud DNS + Cloud Files.

Before using you should copy `keys.json.example` to `keys.json` and update `keys.json` with your RackSpace Cloud account's API details.

I'm also using a `hosts-aliases.json` file for easier assignment of single hosts by nickname (see `hosts-liases.json.example`).

Once everything is in place you can do something like this:
`fab newlampvhost:sub.domain.com`

## Goals ##

The first most important goal of this projects is to follow the outline below by using this command `newlampvhost cms=wp version=stable server=nickname dbname=xucvio`:

 * Create a new server image on $nickname if last image created more than 8 hours ago, then:
 	* Create an Apache vhost directory structure at /var/www/vhost/$URL/{public,private,backup,log}/
 	* Create an Apache vhost config file at /etc/apache2/sites-available/$URL
 	* Enable the new site: `a2ensite $URL`
 	* Reload Apache configuration: `/etc/init.d/apache2 reload`
 	* Add $URL to RackSpace Cloud DNS via API
 	* Drop install packages for $version of $cms in /var/www/vhost/$URL/public/
 	* Add new MySQL database called $dbname
 	* Add new user called $dbname with full access on database $dbname with random password.
 	* Change permissions on files in /var/www/vhost/$URL/public/*
 	* Display password used for MySQL user.
 	* Verify that each step was accomplished.

With fabric the sequence is a bit different, and to make things more complicated there is an iPython mode.

Try this from your usual terminal: `fab serverls`

To get the console use: `fab console`

### Commands ###

 * `newlampvhost(domain, dbname, installcms=False, ip=False, skipbackup=False)`
 * `apachevhostmk(url)`
 * `apachevhostrm(url, safe=True)`
 * `newmysqldb(dbname)`
 * `newmysqluser(dbname, dbuser, dbpassword=False)`
 * `installwordpress(version, location)`
 * `wwwpermissions(directory)`
 * `dnsmk(domain, location=False, subdomain=False, recordtype='A')`
 * `dnsrm(domain, subdomain=False)`
 * `dnsls(domain=False)`
 * `serverimagemk(wait=False)`
 * `serverimagels(imagename=False,imageid=False)`
 * `serverimageprogress(imageid=False, verbosity=1)`
 * `serverimageprogresswatcher(imageid, delay=23, verbosity=0)`
 * `serverls(instance=False)`
 * `addtohosts(host)`
 * `updatehosts()`
 * `ls(search='~/', att='-la')`
 * `rm(path,att='',safe=True)`
 * `touch(path)`
 * `mkdir(dir)`
 * `cloudfilesupload(source,container)`