from dataclasses import dataclass, field
from ipaddress import ip_address


def environment_config(env):
    """Use deployment names as defaults; explicit IMS_* values take precedence."""
    identity, domain = env.get('sipIdentity', ''), env.get('sipDomain', '')
    server = env.get('sipServer', '')
    defaults = {
        'account_uri': f'sip:{identity}@{domain}' if identity and domain else '',
        'registrar_uri': f'sip:{domain}' if domain else '',
        'proxy_uri': f"sip:{server}:{env.get('sipPort', '5060')};lr" if server else '',
        'interface': env.get('imsInterface', ''),
    }
    return {
        'IMS_' + name.upper(): env.get('IMS_' + name.upper(), defaults.get(name, field.default))
        for name, field in SipSettings.__dataclass_fields__.items()
    }


def sip_uri(value):
    if not isinstance(value, str) or not value.startswith('sip:') or len(value) <= 4 or any(c.isspace() for c in value):
        raise ValueError('Expected a sip: URI without whitespace (TLS is not implemented).')
    return value


@dataclass(frozen=True)
class SipSettings:
    account_uri: str
    registrar_uri: str = ''
    proxy_uri: str = ''
    username: str = ''
    password: str = field(default='', repr=False)
    realm: str = '*'
    # The application and UE sidecar share the pod network namespace.
    # An empty bind address selects the interface IPv4 address, or 0.0.0.0.
    transport: str = 'udp'
    bind_address: str = ''
    port: int = 5062
    interface: str = ''
    public_address: str = ''

    @classmethod
    def from_config(cls, config):
        values = {name: config['IMS_' + name.upper()] for name in cls.__dataclass_fields__}
        try:
            values['port'] = int(values['port'])
        except (ValueError, TypeError) as error:
            raise ValueError('IMS_PORT must be an integer.') from error
        settings = cls(**values)
        sip_uri(settings.account_uri)
        for value in (settings.registrar_uri, settings.proxy_uri):
            if value:
                sip_uri(value)
        if settings.transport not in ('tcp', 'udp'):
            raise ValueError('IMS_TRANSPORT must be tcp or udp.')
        if settings.bind_address:
            ip_address(settings.bind_address)
        if settings.public_address:
            ip_address(settings.public_address)
        if not 0 <= settings.port <= 65535:
            raise ValueError('IMS_PORT must be between 0 and 65535.')
        if bool(settings.username) != bool(settings.password):
            raise ValueError('Set both IMS_USERNAME and IMS_PASSWORD, or neither.')
        return settings
