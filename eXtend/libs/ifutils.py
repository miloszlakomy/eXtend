import netifaces

def get_ip_for_iface(ifname):
    try:
        return netifaces.ifaddresses(ifname)[netifaces.AF_INET][0]['addr']
    except KeyError as e:
        raise ValueError('interface %s has no assigned IPv4 addresses' % ifname)

