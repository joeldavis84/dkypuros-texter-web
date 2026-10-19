#!/usr/bin/env python3

import os
import re
import secrets
import sys

  ## Globals
outputPath=os.environ["outputPath"]
nodeName=os.environ["nodeName"]

  ## Utility Functions
def generateImsi():

  match = re.search(r"(?:^|\.)spoke(\d+)(?:\.|$)", nodeName)

  if not match:
    raise ValueError(f"Could not determine spoke number from nodeName: {nodeName}")

  spokeNumber = int(match.group(1))

  if spokeNumber > 999:
    raise ValueError(f"Spoke number exceeds three-digit allocation: {spokeNumber}")

  mcc = "001"
  mnc = "01"
  spokeId = f"{spokeNumber:03d}"
  randomId = f"{secrets.randbelow(10_000_000):07d}"

  return f"{mcc}{mnc}{spokeId}{randomId}"

randomIMSI=generateImsi()
staticKey="00112233445566778899aabbccddeeff"
staticOPC="63bfa50ee6523365ff14c1f45f88737d"

ueConfig = f"""
uicc0 = {{

  imsi = "{randomIMSI}";
  key = "{staticKey}";
  opc = "{staticOPC}";

  pdu_sessions = (
    {{
      id = 1;
      dnn = "oai";
      type = "IPv4";
      nssai_sst = 1;
      nssai_sd = 0xffffff;
    }},
    {{
      id = 2;
      dnn = "ims";
      type = "IPv4";
      nssai_sst = 1;
      nssai_sd = 0xffffff;
    }}
  );

}}
"""

sys.stdout.write(f"Writing configuration at %s\n" % outputPath )

outputFile = open(outputPath, "w")
outputFile.write(ueConfig)
outputFile.close()
