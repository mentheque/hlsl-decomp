import re
from enum import Enum

from logs import Logger, NotLogger

class MultiModuleLogger:
  def __init__(self, default_logger = None, github_logger = None, git_logger = None, licenses_logger = None):
    if not default_logger:
      default_logger = NotLogger

    def default_if_None(logger):
      return logger if logger is not None else default_logger

    self.github = default_if_None(github_logger)
    self.git = default_if_None(git_logger)
    self.licenses = default_if_None(licenses_logger)

class LicenseGroup(Enum):
  Permissive = 1
  GPL = 2

class LicenseType:
  def __init__(self, name, gh_search_name, unique_prefix, group : LicenseGroup):
    self.gh_search_name = gh_search_name
    self.name = name
    self.unique_prefix = unique_prefix
    self.group = group

# TODO: split extensions into source/not source
class Config:
  def __init__(self,
               language,
               github_token,
               target_file_extensions,
               additional_file_extensions,
               log : MultiModuleLogger,
               repository_list_dir = "dumps",
               git_directory = "cloned_repos",
               scancode_processes = 2,
               scancode_cache_dir = "scancode",
               licenses: [LicenseType] = [],
               shader_stats_dir = "stats"):
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
