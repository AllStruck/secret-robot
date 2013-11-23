#!/usr/bin/python
from __future__ import with_statement

from IPython import embed

from fabric.api import *
from fabric.contrib import files
from fabric.colors import red, green, blue, yellow
from fabric.contrib.files import sed
from fabric.operations import put

import re
import json
import datetime

from cuisine import *
import pyrax
import pyrax.exceptions as exc
import openstack.compute
import clouddns

import digitalocean

now = datetime.datetime.now()
datetime = now.strftime("%Y-%m-%d_%H:%M")


with open('./keys.json') as f:
    keychain = json.load(f)
    pyrax.set_setting("debug", True)
    pyrax.set_setting("region", "DFW")
    pyrax.set_setting("identity_type", "rackspace")
    pyrax.set_credentials(keychain['rackspaceuser'], keychain['rackspaceapikey'])
    cf = pyrax.cloudfiles
    cs = pyrax.cloudservers
    cdns = pyrax.cloud_dns
    dodns = digitalocean.Domain(client_id=keychain['digitaloceanuser'], api_key=keychain['digitaloceanapikey'])
    compute = openstack.compute.Compute(username=keychain['rackspaceuser'], apikey=keychain['rackspaceapikey'])
    dns = clouddns.connection.Connection(keychain['rackspaceuser'], keychain['rackspaceapikey'])

with open('./host-aliases.json') as f:
    hostaliases = json.load(f)
    for key, val in enumerate(env.hosts):
        env.hosts[key] = hostaliases[val]

with open('./host-providers.json') as f:
    hostproviders = json.load(f)
    # for key, val in enumerate(env.hosts):
    #     env.hostproviders[key] = hostproviders[val]

env.user = 'root'

apachevhostroot = '/var/www/vhost/'
apachevhostconfigdir = '/etc/apache2/sites-available/'

nginxvhostroot = '/usr/shared/www/'
nginxvhostconfigdir = '/etc/nginx/sites-available/'


def setup():
    group_ensure("remote_admin")
    user_ensure("admin")
    group_user_ensure("remote_admin", "admin")


def addtohosts(host):
    env.hosts.append(str(host))
    env.host_string = str(host)
    updatehosts()


def updatehosts():
    for key, val in enumerate(env.hosts):
        env.hosts[key] = nicenametohost(val)
        env.host_string = nicenametohost(val)


def lampvhostmk(domain, dbname, parent=False, installcms=False, ip=False, skipbackup=False, silent=False, emailAddress=False):
    if not emailAddress:
        emailAddress = domain + '@allstruck.com'
    if not ip:
        ip = gethostipbyhost(env.host_string)
    if not skipbackup:
        serverimagemk(True)
    if not parent:
        entry, parent = split_subdomain(domain)
    else:
        entry = domain
    dnsmk(domain=parent, subdomain=entry, location=ip)
    apachevhostmk(domain)
    newmysqluserpassword = createrandompassword(13)
    randomauthstuff = "MySQL user (" + dbname + ") password: " + newmysqluserpassword + "\n"
    mysqlmk(dbname, dbname, newmysqluserpassword)
    if installcms == "wordpress" or installcms == "wpcmspro":
        randomprefix = createrandompassword(3) + '_'
        randomuser = createrandompassword(5)
        randompassword = createrandompassword(23)
        passwordstore(server=env.host_string, service="WordPress/"+dbname+"/adminuser", user=randomuser, password=randompassword)
        passwordstore(server=env.host_string, service="WordPress/"+dbname, user="dbprefix", password=randomprefix)
        randomauthstuff += 'WP Table Prefix: ' + randomprefix + "\n"
        randomauthstuff += 'WP Admin User: ' + randomuser + "\n"
        randomauthstuff += 'WP Admin Password: ' + randompassword + "\n"
        local('security add-internet-password -a '+randomuser+' -s '+domain+' -r http -w '+randompassword+' -T "" -D "Web form password" -t mrof')
    if installcms == "wordpress":
        with cd(apachevhostroot + domain + '/public/'):
            wordpressdownload('stable', apachevhostroot + domain + '/public/')
            run('wp core config --dbname='+dbname+' --dbuser='+dbname+' --dbpass='+newmysqluserpassword+' --dbhost=localhost'+' --dbprefix='+randomprefix)
            run('wp core install --url='+domain+' --title='+domain+' --admin_name='+randomuser+' --admin_password='+randompassword+' --admin_email='+emailAddress)
            put(local_path=os.getcwd()+"/wp-cli.yml", remote_path='./wp-cli.yml')
            run('wp option update uploads_use_yearmonth_folders 0')
            run('wp rewrite structure /%postname%/')
            run('wp rewrite flush --hard')
            run('wp plugin install wordpress-seo --activate')
            run('wp plugin install google-analytics-for-wordpress')
            run('wp plugin install developer')
            run('wp plugin install types')
            run('wp plugin install woocommerce')
            run('wp plugin install jetpack')
            run('wp plugin install w3-total-cache')
            run('wp plugin install http://db792452fba63cb630b7-494dd5f25ead0ca5c6062a6a9e84232b.r79.cf1.rackcdn.com/gravityforms.zip')
            run('wp theme install http://db792452fba63cb630b7-494dd5f25ead0ca5c6062a6a9e84232b.r79.cf1.rackcdn.com/headway.zip')
            run('wp theme install http://db792452fba63cb630b7-494dd5f25ead0ca5c6062a6a9e84232b.r79.cf1.rackcdn.com/allstruck-headway.zip --activate')
            run('wp plugin install https://github.com/AllStruck/custom-post-type-archive-menu/archive/master.zip --activate')

            run('wp option update timezone_string America/Phoenix')
            run('wp option update time_format "g:i A"')
            run('wp option update date_format "F jS, Y"')
            run('wp option update start_of_week Sunday')
            run('wp option update blog_public 0')
            run('wp option update uploads_use_yearmonth_folders 0')
            run('wp post create --post_type=page --post_status=publish --post_title=Home --post_content="Sample home page content."')
            run('wp post create --post_type=page --post_status=publish --post_title=News')
            run('wp post delete 2 --force')
            run('wp option update show_on_front page')
            run('wp option update page_on_front 3')
            run('wp option update page_for_posts 4')
            wwwpermissions(apachevhostroot + domain + '/public/')
    elif installcms == "wpcmspro":
        wordpressdevcopy(domain,dbname,dbname,newmysqluserpassword,randomprefix)
    print randomauthstuff

def lampvhostrm(domain):
    pass

def apachevhostmk(url, skipenable=False):
    with cd(apachevhostroot):
        run('mkdir ' + url)
        with cd('./' + url):
            run('mkdir public log backup')
            run('chown www-data public')
    with cd(apachevhostconfigdir):
        replacements = {
            'root_dir': apachevhostroot + url,
            'public_dir': apachevhostroot + url + '/public',
            'admin_email': getadminemail(url),
            'domain': url,
            'datetime': datetime + ' MST -0700'
        }
        print 'Uploading template...'
        files.upload_template(filename=os.getcwd()+"/apache-vhost-template.conf", destination=apachevhostconfigdir+url, context=replacements)
        if not skipenable:
            a2('ensite', url)
            a2('reload')

def nginxvhostmk(url, skipenable=False):
    with cd(nginxvhostroot):
        run('mkdir ' + url)
        with cd('./' + url):
            run('mkdir public log backup')
            run('chown www-data public')
    with cd(nginxvhostconfigdir):
        replacements = {
            'root_dir': nginxvhostroot + url,
            'public_dir': nginxvhostroot + url + '/public',
            'admin_email': getadminemail(url),
            'domain': url,
            'datetime': datetime + ' MST -0700'
        }
        print 'Uploading template...'
        files.upload_template(filename=os.getcwd()+"/nginx-vhost-template.conf", destination=nginxvhostconfigdir+url, context=replacements)
        if not skipenable:
            nginx('ensite', url)
            nginx('reload')


def apachevhostrm(url, safe=True):
    safe = safe == True
    with settings(warn_only=True):
        a2('dissite', url)
        a2('reload')
        rm(apachevhostroot + url, '-rf', safe=safe)
        rm(apachevhostconfigdir + url, safe=safe)


def mysqldbls(search=False):
    query = "SHOW DATABASES"
    if search:
        query += ' LIKE \'' + search + '\''
    sqlrootpassword = passwordstore(server=env.host_string, service="mysql")
    with shell_env(SQLROOTPWD=sqlrootpassword):
        run('mysql -uroot -p$SQLROOTPWD -e "' + query + '"')


def mysqlmk(dbname, dbuser, dbpassword=''):
    hprint("Creating MySQL database and user.")
    mysqldbmk(dbname)
    mysqlusermk(dbname, dbuser, dbpassword)


def mysqlrm(dbname, dbuser, safe=True):
    hprint("Removing MySQL database and user.")
    safe = safe == True
    mysqldbrm(dbname, safe)
    mysqluserrm(dbuser)


def mysqldbmk(dbname):
    lprint("Creating MySQL database.")
    with shell_env(SQLROOTPWD=passwordstore(server=env.host_string, service='mysql')):
        run('mysqladmin --user=root --password=$SQLROOTPWD create ' + dbname)


def mysqldbbak(dbname):
    lprint("Backing up MySQL database dump.")
    with shell_env(SQLROOTPWD=passwordstore(server=env.host_string, service='mysql')):
        with cd('~'):
            mysqldumpfile = dbname+'-'+datetime+'.sql'
            run('mysqldump --result-file='+mysqldumpfile+' --databases ' + dbname + ' --user=root --password=$SQLROOTPWD')
            rm(mysqldumpfile)


def mysqldbrm(dbname, safe):
    lprint("Removing MySQL database.")
    with shell_env(SQLROOTPWD=passwordstore(server=env.host_string, service='mysql')):
        if safe:
            mysqldbbak(dbname)
        run('mysqladmin --user=root --password=$SQLROOTPWD drop ' + dbname)


def mysqlusermk(dbname, dbuser, dbpassword=''):
    lprint("Creating MySQL user and attaching to database.")
    if dbpassword == '':
        dbpassword = createrandompassword()
    query = '"GRANT ALL PRIVILEGES ON ' + dbname + '.* TO \'' + dbuser + '\'@\'localhost\' IDENTIFIED BY \'' + dbpassword + '\'"'
    with shell_env(SQLROOTPWD=passwordstore(server=env.host_string, service='mysql', user='root')):
        run('mysql --user=root --password=$SQLROOTPWD -e ' + query)
        servicepath = 'mysql/'+dbname
        passwordstore(server=env.host_string, service=servicepath, user=dbuser, password=dbpassword)
        run('mysql --user=root --password=$SQLROOTPWD -e "FLUSH PRIVILEGES"')


def mysqluserrm(dbuser):
    hprint("Removing MySQL User " + dbuser)
    with shell_env(SQLROOTPWD=passwordstore(server=env.host_string, service='mysql', user='root')):
        run('mysql --user=root --password=$SQLROOTPWD -e "DROP USER \'' + dbuser + '\'@\'localhost\'"')


def getadminemail(subject='admin'):
    return subject + '@' + str(getdomainfromhost(env.host_string))


def wordpressdownload(version, location):
    lprint("Downloading WordPress.")
    # version_commands = {
    #     'stable': 'svn co http://core.svn.wordpress.org/tags/3.5.2 .',
    #     'trunk': 'svn co http://core.svn.wordpress.org/trunk/ .'
    # }
    with cd(location):
        run("wp core download")
        # run(version_commands[version])


def testfind(location="test.allstruck.org"):
    with cd('/var/www/vhost/test.allstruck.org/public'):
        run('find ./ -type f -print0 | xargs -0 sed -i "s/wp-install-template.allstruck.org/' + location + '/g"')

def wordpressdevcopy(location, dbname, dbuser, dbpass, dbprefix):
    hprint("Creating copy of WordPress Dev install.")
    eprint("THIS DOES NOT WORK, QUITTING...")
    return

    with cd('/var/www/vhost/' + location + '/public'):
        lprint("Moving files...")
        run('cp -a /var/www/vhost/wp-install-template.allstruck.org/public/* ./')
        lprint("Replacing old url with new...")
        run('find ./wp-content/themes/ -type f -exec sed -i "s#wp-install-template.allstruck.org#'+ location +'#g" {} \;')
        run('find ./wp-content/plugins/ -type f -exec sed -i "s#wp-install-template.allstruck.org#'+ location +'#g" {} \;')
        run('find ./wp-content/cache/ -type f -exec sed -i "s#wp-install-template.allstruck.org#'+ location +'#g" {} \;')
        run('find ./wp-content/*.php -type f -exec sed -i "s#wp-install-template.allstruck.org#'+ location +'#g" {} \;')
        lprint('Adding new settings to wp-config.php')
        sed("./wp-config.php", "asu_", dbprefix, flags="m")
        run('sed -i "s#define(\'DB_NAME\', \'wpinstalltemp\')#define(\'DB_NAME\', \''+dbname+'\')#mg" wp-config.php')
        run('sed -i "s#define(\'DB_USER\', \'wpinstalltemp\')#define(\'DB_NAME\', \''+dbuser+'\')#mg" wp-config.php')
        run('sed -i "s#define(\'DB_PASSWORD\', \'[^\']*\')#define(\'DB_NAME\', \''+dbpass+'\')#mg" wp-config.php')
        # sed("./wp-config.php", "define(\'DB_NAME\', \'wpinstalltemp\')", "define(\'DB_NAME\', \'" + dbname + "\')")
        # sed("./wp-config.php", "define(\'DB_USER\', \'wpinstalltemp\')/define(\'DB_USER\', \'" + dbuser + "\')")
        # sed("./wp-config.php", "define(\'DB_PASSWORD\', \'[^\']*\')", "define(\'DB_PASSWORD\', \'" + dbpass + "\')")

    lprint('Now handling the database...')
    # with cd('/var/www/vhost/wp-install-template.allstruck.org/public/'):
    #     run('wp db export')
    # with cd('/var/www/vhost/' + location + '/backup'):
    #     with shell_env(SQLROOTPWD=passwordstore(server=env.host_string, service='mysql', user='root')):
    #         templatedbname = 'wpinstalltemp'
    #         mysqldumpfilename = 'wpinstalltemp.sql'
    #         lprint('Export:')
    #         run('mysqldump -n --quick --result-file='+mysqldumpfilename+' --databases ' + templatedbname + ' --user=root --password=$SQLROOTPWD')
    #         lprint('Replace:')
    #         run('sed -i "s#wp-install-template.allstruck.org#'+location+'#mg" ' + mysqldumpfilename)
    #         run('sed -i "s#\'asu_#\''+dbprefix+'#mg" ' + mysqldumpfilename)
    #         run('sed -i "s#\\\`asu_#\\\`'+dbprefix+'#mg" ' + mysqldumpfilename)
    #         # sed(mysqldumpfilename, "wp-install-template.allstruck.org", location)
    #         # sed(mysqldumpfilename, '\x27asu_', '\x27' + dbprefix)
    #         # sed(mysqldumpfilename, "`asu_", "`" + dbprefix)
    #         lprint('Import:')
    #         run('mysql --user=root --password=$SQLROOTPWD ' + dbname + ' < ' + mysqldumpfilename)

def wpcli(domain,command,parameters):
    with cd('/var/www/vhost/'+domain+'/public/'):
        run('wp ' + command+' '+parameters)

def wwwpermissions(directory):
    with cd(directory):
        run('chown -R www-data .')


def aptupdate():
    run('sudo apt-get update')


def aptupgrade():
    run('sudo apt-get upgrade')


def dnsls(domain=False):
    if hostproviders[env.host_string] == 'rackspace-cloud':
        if domain:
            try:
                domain = cdns.find(name=domain)
                print '%-32s %-7s => %-100s' % ('Name:', 'Type:', 'Data:')
                for record in cdns.list_records(domain):
                    print '%-32s %-7s => %100s' % (record.name, '['+record.type+']', record.data)
            except exc.NotFound as e:
                print "Domain (" + domain + ") not found."
        else:
            print '%-32s %-7s %32s' % ('Name:', 'Id:', 'Email Address:')
            for domain in cdns.get_domain_iterator():
                print '%-32s %-7s %32s' % (domain.name, domain.id, domain.emailAddress)
    elif hostproviders[env.host_string] == 'digitalocean':
        manager = digitalocean.Manager(client_id=keychain['digitaloceanuser'], api_key=keychain['digitaloceanapikey'])
        response = manager.get_all_domains()
        if domain:
            try:
                domainid = [item.id for item in response
                            if re.search(item.name,domain+'$')]
                domain_name = [item.name for item in response
                            if re.search(item.name,domain+'$')]
                if len(domainid) > 1:
                    eprint('Major problem, we got more than one matching domain ID back from DO!')
                elif len(domainid) == 1:
                    try:
                        domainid = domainid[0]
                        domain_name = domain_name[0]
                        domain_object = digitalocean.Domain(client_id=keychain['digitaloceanuser'], api_key=keychain['digitaloceanapikey'],id=domainid)
                        records = domain_object.get_records()
                        domain_object = domain_object.load()
                        hprint('Records in ' + domain_name)
                        print '%-32s %-7s %32s' % ('Name:', 'Id:', 'Type:')
                        for record in records:
                            print '%-32s %-7s %32s' % (record.name, record.id, record.record_type)
                    except Exception as e:
                        print "Couldn't get records", e
                else:
                    eprint("Couldn't find that domain from DO: " + domain)
            except Exception as e:
                print "Couln't pull domain from DO", e
        else:
            for domain in response:
                print str(domain.id) + ': ' + domain.name



def dnsmk(domain, subdomain=False, location=False, recordtype='A'):
    if not location:
        location = gethostipbyhost(nicenametohost(env.host_string))
    elif location in hostaliases:
        location = gethostipbyhost(nicenametohost(location))

    if hostproviders[env.host_string] == 'rackspace-cloud':
        if subdomain and subdomain != domain:
            print "Creating RackSpace DNS record in " + domain + " for " + subdomain + " at " +location + " type: " + recordtype
            try:
                dom = cdns.find(name=domain)
            except exc.NotFound:
                answer = raw_input("The domain '%s' was not found. Do you want to create "
                        "it? [y/n]" % domain_name)
                if not answer.lower().startswith("y"):
                    sys.exit()
                try:
                    dom = cdns.domain(name=domain, emailAddress=domain+'@allstruck.com',
                            ttl=900, comment="Created while creating " + subdomain)
                except exc.DomainCreationFailed as e:
                    print "RS Domain creation failed:", e
                print "RS Domain created:", dom
                print
            record = {
                "type": recordtype,
                "name": subdomain,
                "data": location,
                "ttl": 7000
            }
            try:
                recs = dom.add_records([record])
                print recs
                print
            except exc.DomainRecordAdditionFailed as e:
                print "Subdomain creation failed:", e
        else:
            record = {
                "type": recordtype,
                "name": domain,
                "data": location,
                "ttl": 6000
            }
            try:
                dom = cdns.find(name=domain)
                print "Creating main record in " + domain
                dom.add_records([record])
                print "Added main record to existing domain."
            except exc.NotFound as e:
                print "Creating root domain " + domain
                dom = cdns.create(name=domain, ttl=300, emailAddress=domain + '@allstruck.com')
                dom.add_records([record])
                print "Added domain and main record."
            print
    elif hostproviders[env.host_string] == 'digitalocean':
        domanager = digitalocean.Manager(client_id=keychain['digitaloceanuser'], api_key=keychain['digitaloceanapikey'])
        dodomains = domanager.get_all_domains()
        if subdomain and subdomain != domain:
            hprint("Creating Digital Ocean DNS record in " + domain + " for " + subdomain + " at " + location + " type: " + recordtype)
            try:
                domainid = [item.id for item in dodomains
                            if item.name == domain]
                domain_name = [item.name for item in dodomains
                            if re.search(item.name,domain+'$')]
                if len(domainid) > 1:
                    eprint('Major problem, we got more than one matching domain ID back from DO!')
                elif len(domainid) == 1:
                    try:
                        domainid = domainid[0]
                        domain_name = domain_name[0]
                        hprint('Creating record under ' + domain_name + ': ' + subdomain)
                        dorecordmk(domainid, recordtype, location, subdomain)
                    except Exception as e:
                        print "Record could not be created on DO:", e
                else:
                    print "This domain was not found on DO:", domain
            except Exception as e:
                print "Error when pulling existing domain ID", e
        else:
            hprint("Creating Digital Ocean DNS record for " + domain + " at " + location + " type: " + recordtype)
            try:
                domainid = [item.id for item in dodomains
                            if re.search(item.name,domain+'\.$')]
                domain_name = [item.name for item in dodomains
                            if re.search(item.name,domain+'\.$')]
                if len(domainid) > 1:
                    eprint('Major problem, we got more than one matching domain back from DO!')
                elif len(domainid) == 1:
                    try:
                        domainid = domainid[0]
                        domain_name = domain_name[0]
                        subdomain = domain.replace('.'+domain_name, '')
                        lprint('Auto creating subdomain record under ' + domain_name + ': ' + subdomain)
                        dorecordmk(domainid, recordtype, location, subdomain)
                    except Exception as e:
                        print "Record could not be created on DO:", e
                else:
                    print "This domain does not appear to be a subdomain of another, going to create a new top level record now..."
                    try:
                        lprint("Creating domain " + domain + " at " + location)
                        domain = digitalocean.Domain(client_id=keychain['digitaloceanuser'], api_key=keychain['digitaloceanapikey'],name=domain,ip_address=location)
                        domain.create()
                    except Exception as e:
                        print "Domain creation failed:", e
                        print
            except Exception as e:
                print "Problem with trying to look for matching domain."

def dnsrm(domain, subdomain=False, record_type='A'):
    if hostproviders[env.host_string] == 'rackspace-cloud':
        try:
            dom = cdns.find(name=domain)
        except exc.NotFound as e:
            print "That domain (" + domain + ") wasn't found!"
            sys.exit()
        if subdomain:
            try:
                rec = dom.find_record(record_type, name=subdomain)
                rec.delete()
            except exc.NotFound as e:
                print "That record wasn't found... ", e
                hprint("This is not a toy!")
                sys.exit()
        else:
            dom.delete()
    elif hostproviders[env.host_string] == 'digitalocean':
        try:
            manager = digitalocean.Manager(client_id=keychain['digitaloceanuser'], api_key=keychain['digitaloceanapikey'])
            response = manager.get_all_domains()
            domainid = [item.id for item in response
                        if item.name == domain]
            if len(domainid) > 1:
                eprint('Major problem, we got more than one matching domain ID back from DO!')
            elif len(domainid) == 1:
                try:
                    domainid = domainid[0]
                    domain_object = digitalocean.Domain(client_id=keychain['digitaloceanuser'], api_key=keychain['digitaloceanapikey'],id=domainid)
                    if subdomain:
                        response = domain_object.get_records()
                        record_id = [item.id for item in response
                                    if item.name+'.' == subdomain]
                        if len(record_id) > 1:
                            eprint('Major problem, we got more than one matching domain record ID back from DO!')
                        elif len(record_id) == 1:
                            record_object = digitalocean.Record(client_id=keychain['digitaloceanuser'], api_key=keychain['digitaloceanapikey'], domain_id=domainid, id=record_id[0])
                            record_object.destroy()
                            hprint("Removed subdomain: " + subdomain + " from domain: " + domain + " from Digital Ocean DNS")
                        else:
                            eprint("Couldn't find that subdomain captain!")
                    else:
                        domain_object.destroy()
                        hprint("Removed domain: " + domain + " with ID of: " + str(domainid) + " from Digital Ocean DNS")
                except Exception as e:
                    print "Domain could not be removed from DO:", e
            else:
                print "This domain was not found on DO:", domain
        except Exception as e:
            print "Domain could not be retrieved from DO:", e

def dorecordmk(domainid, recordtype, location, subdomain):
    record_object = digitalocean.Record(domain_id=domainid, client_id=keychain['digitaloceanuser'],
                                        api_key=keychain['digitaloceanapikey'])
    record_object.record_type=recordtype
    record_object.data=location
    record_object.name=subdomain+'.'
    record_object.create()


def serverimagemk(wait=False):
    server = compute.servers.find(name=getserverbyname(env.host_string))
    compute.images.create(getserverbyname(env.host_string) + '-' + datetime, server)
    image = compute.images.find(name=getserverbyname(env.host_string) + '-' + datetime)
    if wait:
        print "Waiting for server image to complete."
        server_image_progress_watcher(image.id)


def serverimagels(imagename=False, imageid=False):
    if imagename or imageid:
        if imageid:
            image = compute.images.get(imageid)
            print str(image) + ' {imageid=' + str(image.id) + '} ' + serverimagestatus(image.status)
            if image.status == 'SAVING':
                print 'Progress: ' + str(image.progress) + '%'
            print 'Created: ' + str(image.created)
            print 'Updated: ' + str(image.updated)
        else:
            images = compute.images.list()
            for image in images:
                if imagename in image.name:
                    print str(image) + ' {imageid=' + str(image.id) + '} ' + serverimagestatus(image.status)
                    if image.status == 'SAVING':
                        print 'Progress: ' + str(image.progress) + '%'
                    print 'Created: ' + str(image.created)
                    print 'Updated: ' + str(image.updated)
                    print '---'
    else:
        images = cs.images.list()
        for image in images:
            print image


def listbaseimages():
    for image in cs.list_base_images():
        print image  # '%s %s' % (image)


def serverimagestatus(status):
    if status == 'ACTIVE':
        return green(status)
    elif status == 'QUEUED':
        return yellow(status)
    elif status == 'SAVING':
        return blue(status)
    else:
        return red(status)


def serverimageprogress(imageid=False, verbosity=1):
    if not imageid:
        print "ERROR: Must provide imageid=id"
        return -1
    if not server_image_is_complete(imageid, 0):
        image = compute.images.get(imageid)
        if hasattr(image, 'status'):
            if image.status == 'SAVING':
                if hasattr(image, 'progress'):
                    if verbosity > 0:
                        print 'Progress: ' + str(image.progress) + '%'
                        return image.progress
                else:
                    return 0
            elif image.status == 'QUEUED':
                if verbosity > 0:
                    print 'Queued'
                return 0
            else:
                if verbosity > 0:
                    print '100% Complete'
        else:
            if verbosity > 0:
                print "There's not a status property on image :("
            return 0
    else:
        if verbosity > 0:
            print "100% Complete"
        return 100


def server_image_is_complete(imageid=False, verbosity=1):
    if not imageid:
        print "ERROR: Must provide imageid=id"
        return
    image = compute.images.get(imageid)
    if image.status == 'SAVING':
        if verbosity > 0:
            print 'Not done.'
        return False
    elif image.status == 'ACTIVE':
        if verbosity > 0:
            print 'Complete!'
        return True
    elif image.status == 'QUEUED':
        if verbosity > 0:
            print 'You entered the Queue, this is going to suck...'
        return False
    else:
        print 'Problem! image.status is: ' + str(image.status)
        return


def server_image_progress_watcher(imageid, delay=23, verbosity=0):
    import time
    if not imageid:
        print "ERROR: Must provide imageid=id"
        return
    while not server_image_is_complete(imageid, verbosity):
        now = datetime.datetime.now()
        datetime = now.strftime("%Y-%m-%d_%H:%M")
        print datetime + ' ' + str(serverimageprogress(imageid, verbosity)) + '%'
        time.sleep(delay)


def cloudserverls(instance=False):
    if instance:
        servers = compute.servers.findall(name=getserverbyname(instance))
        for server in servers:
            print 'Name: ' + server.name
    else:
        # print cs.servers.list()
        # for server in servers:
        #   print server.name, "  -- ID:", server.id
        servers = compute.servers.list();
        for server in servers:
            print server
            details = compute.servers.get(server)
            print 'Status: ' + details.status
            if details.status == 'ACTIVE':
                print 'Addresses: ' + str(details.addresses)
            else:
                print 'Progress: ' + str(details.progress)
            print ''


def split_subdomain(domain):
    entry = parent = domain
    if domain.count('.') > 1:
        entry = domain
        parent = domain[domain.rfind('.', 0, domain.rfind('.'))+1:]
    return entry, parent


def gethostipbyhost(host):
    ipaddresses = {
        'allstruck.com':        '198.101.193.150',
        'allstruck.net:42123':  '204.232.207.253',
        'allstruck.org:42123':  '204.232.201.73',
        '64.49.246.208':        '64.49.246.208',
        'showstat.us':          '192.241.204.120',
        'nginx.showstat.us':    '192.241.230.20',
        '162.243.151.162':      '162.243.151.162'
    }
    return ipaddresses[host]


def getserverbyname(host, lower=False):
    names = {
        'allstruck.com':        'Archimedes',
        'allstruck.net:42123':  'AllStruckClients',
        'allstruck.org:42123':  'McKay',
        '64.49.246.208':        'Cooper',
        'showstat.us':          'Carter',
        '162.243.151.162':      'Maxwell'
    }
    result = ''
    if host in names:
        if names[host]:
            result = names[host]
        else:
            result = names[names.index(host)]
    if lower:
        return result.lower()
    else:
        return result


def getdomainfromhost(host):
    domains = {
        'allstruck.com':        'allstruck.com',
        'allstruck.net:42123':  'allstruck.com',
        'allstruck.org:42123':  'allstruck.com',
        '64.49.246.208':        'allstruck.com',
        'showstat.us':          'allstruck.com',
        'nginx.showstat.us':    'allstruck.com',
        '162.243.151.162':      'allstruck.com'
    }
    return domains[host]


def a2(task='', att=''):
    tasks = {
        'restart': "run('service apache2 restart')",
        'reload': "run('service apache2 reload')",
        'ensite': "run('a2ensite ' + att)",
        'dissite': "run('a2dissite ' + att)",
        'enmod': "run('a2enmod ' + att)",
        'dismod': "run('a2dismod ' + att)",
        'sites-available': "ls('" + apachevhostconfigdir + "')",
        'sites-enabled': "ls('" + apachevhostconfigdir + "../sites-enabled')",
        'sites-files': "run('ls " + apachevhostroot + "')"
    }
    eval(tasks[task])

def nginx(task='', att=''):
    tasks = {
        'restart': "run('nginx restart')",
        'reload': "run('nginx reload')",
        'ensite': "run('nginex_ensite ' + att)",
        'dissite': "run('nginex_dissite ' + att)",
        'sites-available': "ls('" + nginxvhostconfigdir + "')",
        'sites-enabled': "ls('" + nginxvhostconfigdir + "../sites-enabled')",
        'sites-files': "run('ls " + nginxvhostroot + "')"
    }
    eval(tasks[task])


def nicenametohost(nicename):
    if nicename in hostaliases:
        return hostaliases[nicename]
    return nicename


def hosttonicename(host):
    nicenames = {
        'allstruck.com': 'archimedes',
        'allstruck.net:42123': 'clients',
        'allstruck.org:42123': 'mckay',
        '64.49.246.208': 'cooper',
        'showstat.us': 'carter',
        '162.243.151.162': 'maxwell'
    }
    if nicenames.has_key(host):
        return nicenames[host]
    return False


def createrandompassword(length=8):
    import string
    from random import choice
    chars = string.letters + string.digits
    return ''.join(choice(chars) for _ in xrange(length))


def passwordstore(server=env.host_string, service='system', user='root', password=False, verbose=False):
    if nicenametohost(server):
        server = hosttonicename(nicenametohost(server))
    from firebase.firebase import FirebaseApplication, FirebaseAuthentication
    authentication = FirebaseAuthentication(keychain['firebaseapikey'], True, True)
    fbase = FirebaseApplication(keychain['firebaseappurl'], authentication)
    if password:
        resourcepath = '/passwords/' + server + '/' + service
        data = {
            user: password
        }
        if verbose:
            print "Posting " + str(data) + " to " + resourcepath
        result = fbase.patch(resourcepath, data, params={'print': 'pretty'}, headers={'X_FANCY_HEADER': 'VERY FANCY'})
        if verbose:
            print result
        return result
    else:
        resourcepath = '/passwords/' + server + '/' + service + '/' + user
        password = fbase.get(resourcepath, None)
        if verbose:
            print resourcepath + ':'
            print password
        return password

def ls(search='~/', att='-la'):
    run('ls --color ' + att + ' ' + search)


def rm(path, att='', safe=True):
    if safe:
        with shell_env(OS_USERNAME=keychain['rackspaceuser'], OS_API_KEY=keychain['rackspaceapikey'], OS_PASSWORD=keychain['rackspaceapikey'], OS_AUTH_URL='https://identity.api.rackspacecloud.com/v2.0/', OS_REGION_NAME='dfw'):
            if path[-4:] == '.zip':
                run('turbolift -r dfw upload --source '+path+' --container secret-robot-safe-delete')
                run('rm ' + att + ' ' + path)
            else: 
                # Zip contents of file or directory (and remove contents),
                #  upload to cloud files, then delete zip file:
                tempzipfilename = path+'-'+datetime+'.zip'
                run('zip -rTm '+tempzipfilename+' '+path)
                cloudfilesput(tempzipfilename, 'secret-robot-safe-delete', host=env.host_string)
                run('rm ' + tempzipfilename)
    else:
        run('rm ' + att + ' ' + path)


def touch(path):
    run('touch ' + path)


def mkdir(dir):
    run('mkdir ' + dir)


def cloudfilesput(source,container='secret-robot-safe-delete',host=env.host_string):
    with shell_env(OS_USERNAME=keychain['rackspaceuser'], OS_API_KEY=keychain['rackspaceapikey'], OS_PASSWORD=keychain['rackspaceapikey'], OS_AUTH_URL='https://identity.api.rackspacecloud.com/v2.0/', OS_REGION_NAME='dfw'):
        run('turbolift -r dfw upload --source ' + source + ' --container ' + container)


def cloudfilesls(container=False):
    if container:
        print "Contents of container '" + container + "':"
        cont = cf.get_container(container)
        objects = cont.get_objects()

        for obj in objects:
            print obj
    else:
        print "List of all containers:"
        for container in cf.list_containers():
            print container


def eprint(message):
    print '!'*80
    print message.upper()
    print '!'*80

def hprint(message):
    print '#'*80
    print message.upper()
    print '#'*80

def lprint(message):
    print message
    print '-'*80


def echo(message):
    run('echo ' + message)


def console():
    embed()  # IPython


def c():
    console()