from __future__ import with_statement
from fabric.api import *
from fabric.contrib.console import confirm

from cuisine import *

with open('./keys.json') as f:
	env = json.load(f)

import clouddns
dns = clouddns.connection.Connection(env.rackspace-user, env.rackspace-api-key)

env.warn_only = True
env.hosts = ['allstruck.org:42123']
env.user = 'root'

vhostroot = '/var/www/vhost/'

def setup():
	group_ensure("remote_admin")
	user_ensure("admin")
	group_user_ensure("remote_admin", "admin")

def dovhostcommand(vhost, command):
	location = vhostroot + vhost + 'public/'
	if "wwwpermissions" in command:
		wwwpermissions(location)

def splitsubdomain(domain):
	entry = parent = domain
	if domain.count('.') > 1:
		entry = domain
		parent = domain[domain.rfind('.',0,domain.rfind('.'))+1:]
	return entry,parent

def gethostip(host):
	ipaddresses = {
		'allstruck.com': 		'198.101.193.150',
		'allstruck.net': 		'204.232.207.253',
		'allstruck.org:42123': 	'204.232.201.73',
		'cooper':				'50.56.239.226'
	}
	return ipaddresses[host]

def createrandompassword(length=8):
	import string
	from random import sample, choice
	chars = string.letters + string.digits
	return ''.join(choice(chars) for _ in xrange(length))

def newlampvhost(domain, dbname, installcms=False, ip=False):
	if not ip:
		ip = gethostip(env.host_string)
	entry,parent = splitsubdomain(domain)
	dnsmk(parent,ip,entry)
	newapachevhost(domain)
	newmysqldb(dbname)
	newmysqluserpassword = createrandompassword()
	print "New user password: " + newmysqluserpassword
	newmysqluser(dbname, dbname, newmysqluserpassword)
	if installcms == "wordpress":
		installwordpress(stable, vhostroot + domain + 'public/')
		wwwpermissions(vhostroot + domain + 'public/')

def newapachevhost(url):
	run('a2newsite ' + url)

def newmysqldb(dbname):
	run('sqlnewdb ' + dbname)

def newmysqluser(dbname, dbuser, dbpassword):
	run('sqlnewdbuser ' + dbname + ' ' + dbuser)

def installwordpress(version, location):
	version_commands = {
		'stable': 'svn co http://core.svn.wordpress.org/tags/3.5.2 .',
		'trunk':'svn co http://core.svn.wordpress.org/trunk/ .'
	}
	run('cd ' + location)
	run(version_commands[version])

def wwwpermissions(directory):
	run('cd ' + directory)
	run('chown www-data -R ./*')

@hosts('allstruck.org')
def dnsmk(domain, location=False, subdomain=False, recordtype='A'):
	print "Starting DNSMK task"
	print "Domain = " + domain
	print "Location = " + location
	print "Subdomain = " + subdomain
	if subdomain and subdomain != domain:
		print "Creating record in " + domain + " for " + subdomain + " at " +location + " type: " + recordtype
		parent = dns.get_domain(name=domain)
		parent.create_record(subdomain, location, recordtype)
	else:
		if dns.get_domain(name=domain):
			print "Creating main record in " + domain
			dns.create_record(subdomain, location, recordtype)
		else:
			print "Creating root domain " + domain
			dns.create_domain(name=domain, ttl=300, emailAddress=domain + '@allstruck.com')

@hosts('allstruck.org')
def dnsrm(domain, subdomain=False):
	try:
		domain = dns.get_domain(name=domain)
	except ValueError:
		print "That domain (" + domain + ") doesn't work!"
	if subdomain:
		try:
			record = domain.get_record(name=subdomain)
		except ValueError:
			print "That subdomain (" + subdomain + " doesn't work!"
		domain.delete_record(record.id)
	else:
		dns.delete_domain(domain.id)

@hosts('allstruck.org')
def dnsls(domain=False):
	if domain:
		domain = dns.get_domain(name=domain)
		for record in domain.get_records():
			print '(%s) %s -> %s' % (record.type, record.name, record.data)
	else:
		for domain in dns.get_domains():
			print domain.name

def sysupdate():
	run('sudo apt-get update')

def sysupgrade():
	run('sudo apt-get upgrade')
