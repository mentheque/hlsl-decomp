import re
from enum import Enum
import json

from logs import Logger, NotLogger

class MultiModuleLogger:
  def __init__(self, default_logger = None, github_logger = None, git_logger = None, licenses_logger = None,
               export_logger = None, compile_logger = None):
    if not default_logger:
      default_logger = NotLogger

    def default_if_None(logger):
      return logger if logger is not None else default_logger

    self.github = default_if_None(github_logger)
    self.git = default_if_None(git_logger)
    self.licenses = default_if_None(licenses_logger)
    self.export = default_if_None(export_logger)
    self.compile = default_if_None(compile_logger)

class LicenseGroup(Enum):
  NoIncludes = 0 # This cannot be used in config.json
  Permissive = 1
  GPL = 2
  Other = 3 # | These cannot be used in config.json
  Unidentified = 4
  Inconclusive = 5
  ExternalFile = 6

class LicenseType:
  def __init__(self, name, gh_search_name, unique_prefix, group : LicenseGroup):
    self.gh_search_name = gh_search_name
    self.name = name
    self.unique_prefix = unique_prefix
    self.group = group

from utils import CompilerTypes

class Config:
  _DEFAULT_VALUES = {
    'additional_file_extensions': [],
    'repository_list_dir': "dumps",
    'git_directory':  "cloned_repos",
    'scancode_processes': 2,
    'scancode_cache_dir': "scancode",
    'licenses': [],
    'shader_stats_dir': "stats",
    'exported_zip_dir': "output",
    'preprocessed_dir' : "preprocessed",
    'compile_directives' : {},
    'fxc_path' : 'fxc',
    'dxc_path' : 'dxc',
    'compiled_dir': "compiled"
  }
  def __init__(self,
               language,
               github_token,
               target_file_extensions,
               log : MultiModuleLogger,
               additional_file_extensions = [],
               repository_list_dir = "dumps",
               git_directory = "cloned_repos",
               scancode_processes = 2,
               scancode_cache_dir = "scancode",
               licenses: [LicenseType] = [],
               shader_stats_dir = "stats",
               exported_zip_dir = "output",
               preprocessed_dir = "preprocessed",
               compile_directives = {},
               fxc_path = 'fxc',
               dxc_path = 'dxc',
               compiled_dir = "compiled"):
    self.language = language
    self.github_token = github_token
    self.file_extensions = target_file_extensions
    self.additional_file_extensions = additional_file_extensions

    self.log = log

    self.repository_list_dir = repository_list_dir
    self.git_directory = git_directory

    self.scancode_processes = scancode_processes
    self.scancode_cache_dir = scancode_cache_dir

    self.licenses = licenses

    self.shader_stats_dir = shader_stats_dir

    self.target_extension_patterns = \
      [re.compile(f'.*\\.{re.escape(ext)}$', re.IGNORECASE) for ext in self.file_extensions]

    self.download_extensions_patterns = \
      [re.compile(f'.*\\.{re.escape(ext)}$', re.IGNORECASE)
       for ext in self.file_extensions + self.additional_file_extensions]

    self.exported_zip_dir = exported_zip_dir
    self.preprocessed_dir = preprocessed_dir

    self.compile_directives = compile_directives
    self.compiler_path = {
      CompilerTypes.FXC: fxc_path,
      CompilerTypes.DXC: dxc_path
    }
    self.compiled_dir = compiled_dir


from logs import EchoLogger, PrefixedLogger
def load_config(path ='config.json') -> Config:
  def errorExit(message: str):
    print("+ Error: " + message)
    print(f"Expected config json location: {path}")
    print("For contents reference visit gitlab")
    raise Exception("Unable to load config")


  print(f"+ Loading config from {path}")
  try:
    with open(path, 'r') as file:
      config_json = json.load(file)

  except FileNotFoundError:
    errorExit("File not found")
  except json.JSONDecodeError:
    errorExit("Invalid JSON format")
  except Exception as e:
    errorExit(f"{e}")

  if not _verifyers['config'](config_json):
    errorExit("Failed to verify json contents against expected schema")

  def get(key):
    return config_json[key]
  def get_or_default(key):
    return config_json.get(key, Config._DEFAULT_VALUES[key])

  return Config(
    language=get('language'),
    github_token=get('github_token'),
    target_file_extensions=get('target_file_extensions'),
    log = MultiModuleLogger(PrefixedLogger("default", EchoLogger(filepath="logs/default_logs.txt"))), # For now
    additional_file_extensions = get_or_default('additional_file_extensions'),
    repository_list_dir = get_or_default('repository_list_dir'),
    git_directory = get_or_default('git_directory'),
    scancode_processes = get_or_default('scancode_processes'),
    scancode_cache_dir = get_or_default('scancode_cache_dir'),
    licenses = [LicenseType(
      ltj['name'],
      ltj['gh_search_name'],
      ltj['unique_prefix'],
      (LicenseGroup.Permissive if ltj['group'] == 'Permissive' else LicenseGroup.GPL)
    ) for ltj in get_or_default('licenses')],
    shader_stats_dir = get_or_default('shader_stats_dir'),
    exported_zip_dir=get_or_default('exported_zip_dir'),
    preprocessed_dir = get_or_default('preprocessed_dir'),
    compile_directives = get_or_default('compile_directives'),
    fxc_path=get_or_default('fxc_path'),
    dxc_path=get_or_default('dxc_path'),
    compiled_dir=get_or_default('compiled_dir')
  )


def _type_verifier(type):
  return (lambda x : isinstance(x, type))

def _list_verifier(member_verifier_key):
  return (lambda l: isinstance(l, list) and all(_verifyers[member_verifier_key](mem) for mem in l))

def _dict_verifier(member_verifier_key):
  return (lambda d: isinstance(d, dict) and all(_verifyers[member_verifier_key](mem) for mem in d.values()))

def _schema_verifier(schema, optionals_schema):
  def inner(js):
    errors = []

    for key in schema.keys():
      if not key in js:
        errors.append(f"Missing {key} key")

    def verify_what_present(source):
      for key in source.keys():
        if key in js and not _verifyers[source[key]](js[key]):
          errors.append(f"Failed to verify {key}. Expecting {source[key]}")

    verify_what_present(schema)
    verify_what_present(optionals_schema)

    if len(errors) > 0:
      for err in errors:
        print(err)
      return False

    return True


  return inner

def _specific_values_verifier(permitted_values):
  return (lambda v : v in permitted_values)

_str_verifier = _type_verifier(str)

_verifyers = {
  'str' : _str_verifier,
  'int' : _type_verifier(int),
  'str_list' : _list_verifier('str'),
  'licence_group' : _specific_values_verifier(["Permissive", "GPL"]),
  'license_type' : _schema_verifier(
    {
      'name' : 'str',
      'gh_search_name' : 'str',
      'unique_prefix' : 'str',
      'group' : 'licence_group'
    },
    {}
  ),
  'license_type_list' : _list_verifier('license_type'),
  'config' : _schema_verifier(
    {
      'language' : 'str',
      'github_token' : 'str',
      'target_file_extensions' : 'str_list'
    },
    {
      'additional_file_extensions' : 'str_list',
      'repository_list_dir' : 'str',
      'git_directory' : 'str',
      'scancode_processes' : 'int',
      'scancode_cache_dir' : 'str',
      'licenses' : 'license_type_list',
      'shader_stats_dir' : 'str',
      'exported_zip_dir' : 'str',
      'preprocessed_dir' : 'str',
      'compile_directives' : 'compile_directives_all',
      'fxc_path' : 'str',
      'dxc_path' : 'str',
      'compiled_dir' : 'str'
    }
  ),

  'additional_directives' : _schema_verifier(
    {},
    {
      'dxc': 'str_list',
      'fxc': 'str_list'
    }
  ),
  'compile_step_additionals' : _dict_verifier('additional_directives'),
  # TODO: add default additionals for all files
  'compile_directives_all' : _schema_verifier(
    {},
    {
      'preprocessing' : 'compile_step_additionals',
      'compilation'   : 'compile_step_additionals'
    }
  )
}
