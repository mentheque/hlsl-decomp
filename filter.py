from config import Config
from utils import Repository

def filter_has_stats(repo_stats, file_json):
  return file_json['path'] not in repo_stats

def _filter_between(value, min_value, max_value):
  return (min_value is not None and value < min_value) or (max_value is not None and value > max_value)

from analyse_file import file_stats, load_repo_stats
def _filter_stat_between(stats_name, min_value, max_value):
  return (lambda repo_stats, file_json:
          _filter_between(file_stats(repo_stats, file_json)[stats_name], min_value, max_value))

def new_filter_line_count(min_lines = None, max_lines = None):
  return _filter_stat_between('lines', min_lines, max_lines)

def new_filter_size(min_size = None, max_size = None):
  return _filter_stat_between('size', min_size, max_size)

def new_filter_unique_hash(config : Config):
  encountered = {}
  def filter(repo_stats, file_json):
    hash = file_stats(repo_stats, file_json)['hash']
    if hash in encountered:
      #config.log.licenses.secondary(f"Hash collision: {encountered[hash]}, {file_json['path']}")
      return True
    else:
      encountered[hash] = file_json['path']
      return False

  return filter

def new_filter_file_extensions(target_extensions):
  def filter(repo_stats, file_json):
    path_str = file_json['path']
    return not any(path_str.endswith('.' + extension) for extension in target_extensions)

  return filter


def filter(config : Config, walked, filters):
  filtered = []
  for repo, file_license_pairs in walked:
    repo_stats = load_repo_stats(config, repo)
    repo_filtered = []
    for file, license in file_license_pairs:
      if not any(filter(repo_stats, file) for filter in filters):
        repo_filtered.append((file, license))

    if len(repo_filtered) > 0:
      filtered.append((repo, repo_filtered))

  return filtered




