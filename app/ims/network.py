"""Wait for the UE data-plane address before opening the SIP transport."""
from dataclasses import replace
from ipaddress import IPv4Address
import json
import subprocess
import time


def interface_address(interface):
    try:
        result = subprocess.run(
            ['ip', '-j', '-4', 'addr', 'show', 'dev', interface],
            capture_output=True, text=True, timeout=3,
        )
    except OSError as error:
        raise RuntimeError('Cannot inspect IMS interface; the ip command is required.') from error
    except subprocess.TimeoutExpired:
        return None
    if result.returncode:
        return None
    for device in json.loads(result.stdout):
        for address in device.get('addr_info', []):
            if address.get('family') == 'inet':
                return str(IPv4Address(address['local']))
    return None


def resolve_network(settings, stopped, timeout=180):
    address = None
    deadline = time.monotonic() + timeout
    while settings.interface and not stopped.is_set():
        address = interface_address(settings.interface)
        if address:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('Timed out waiting for the IMS interface IPv4 address.')
        stopped.wait(1)
    bind_address = settings.bind_address or address or '0.0.0.0'
    return replace(
        settings, bind_address=bind_address,
        public_address=settings.public_address or address or (
            bind_address if bind_address not in ('0.0.0.0', '::') else ''
        ),
    )
