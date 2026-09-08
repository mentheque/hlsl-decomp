import json
import os.path
import traceback
import time

from logs import ConsoleLogger, PrefixedLogger, EchoLogger
from config import Config, MultiModuleLogger, LicenseType, LicenseGroup

from user_dialoge import query
from config import load_config

import subprocess
from utils import join_path

config = load_config()

save_path = join_path(config.decompiled_dir, 'amd/6767')
save_path.parent.mkdir(parents=True, exist_ok=True)
res_6 = subprocess.run(
  [config.decompilator_paths['ocloc'],
   'compile',
    #'-c', 'gfx1100',
   '-dump', str(save_path),
'-file', "C:/Users/menth/Documents/5df75fe1ea9c2ae5f3b6738bde0ac4ffd3ce070405bc31bf65c451e740014373_cs_6_3_CopyToFinal_spirv.spv"
   ]
, capture_output=True, text=True, check=True)

print(res_6.returncode)
print(res_6.stdout)
print(res_6.stderr)