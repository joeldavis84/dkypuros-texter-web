from dataclasses import dataclass, field
from ipaddress import ip_address


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
    # Bind all IPv4 interfaces to receive traffic on the UE data-plane interface.
    transport: str = 'udp'
    bind_address: str = '0.0.0.0'
    port: int = 5062

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
        ip_address(settings.bind_address)
        if not 0 <= settings.port <= 65535:
            raise ValueError('IMS_PORT must be between 0 and 65535.')
        if bool(settings.username) != bool(settings.password):
            raise ValueError('Set both IMS_USERNAME and IMS_PASSWORD, or neither.')
        return settings
