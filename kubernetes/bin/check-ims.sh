#!/usr/bin/env bash

set -euo pipefail

imsInterface="${imsInterface:-}"
sipServer="${sipServer:-192.168.27.57}"
sipPort="${sipPort:-5060}"
sipIdentity="${sipIdentity:-user1}"
sipDomain="${sipDomain:-dkypuros}"

  ## IMS health checking is optional.
  ## An unset or empty imsInterface explicitly means "Do not perform IMS health checking."
if [[ -z "${imsInterface}" ]]; then
  exit 0
fi

  ## Resolve the IPv4 address currently assigned to the configured IMS
  ## interface. Do not infer the IMS interface from its subnet.
if ! imsAddressInfo="$(
  ip -j -4 addr show dev "${imsInterface}" 2>/dev/null
)"; then
  exit 1
fi

imsIp="$(
  echo "${imsAddressInfo}" | 
  jq -r '
    .[0].addr_info[]?
    | select(.family == "inet")
    | .local' |
    head -n 1
)"

  ## The interface was configured for health checking but does not
  ## currently have an IPv4 address.
if [[ -z "${imsIp}" || "${imsIp}" == "null" ]]; then
  exit 1
fi

  ## Unique identifiers for SIP
callId="health-${RANDOM}-$$@${sipIdentity}"
branch="z9hG4bK-health-${RANDOM}"

  ## Exercise the actual IMS path with a harmless SIP OPTIONS request.
  ##
  ## A valid SIP 200 response proves that traffic left through the UE's
  ## IMS PDU session, traversed the 5G user plane, reached Kamailio, and
  ## successfully returned.
response="$(
  {
    printf \
      'OPTIONS sip:%s SIP/2.0\r\nVia: SIP/2.0/UDP %s;branch=%s;rport\r\nFrom: <sip:%s@%s>;tag=health\r\nTo: <sip:%s>\r\nCall-ID: %s\r\nCSeq: 1 OPTIONS\r\nMax-Forwards: 70\r\nContent-Length: 0\r\n\r\n' \
      "${sipDomain}" \
      "${imsIp}" \
      "${branch}" \
      "${sipIdentity}" \
      "${sipDomain}" \
      "${sipDomain}" \
      "${callId}" |
      nc \
        -u \
        -s "${imsIp}" \
        -w 2 \
        "${sipServer}" \
        "${sipPort}"
  } || true
)"

echo "${response}" | grep -q '^SIP/2.0 200'
