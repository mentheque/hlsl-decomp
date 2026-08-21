from config import Config
from utils import Repository

from analyse_file import _file_key
def filter_has_stats(repo_stats, file_json):
  return _file_key(file_json) not in repo_stats

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
      # config.log.licenses.secondary(f"Hash collision: {encountered[hash]}, {file_json['path']}")
      return True
    else:
      encountered[hash] = file_json['path']
      return False

  return filter

def new_filter_file_extensions(target_extensions):
  def filter(repo_stats, file_json):
    path_str = file_json['path'].lower()
    return not any(path_str.endswith('.' + extension) for extension in target_extensions)

  return filter

def _filter_matches_categorical(categorical_type, target_categorical):
  def filter(repo_stats, file_json):
    categorical = file_stats(repo_stats, file_json)[categorical_type]
    return not (target_categorical in categorical and categorical[target_categorical] > 0)

  return filter

def new_filter_platform(target_platform):
  return _filter_matches_categorical('platforms', target_platform)

def new_filter_shader_type(target_type):
  return _filter_matches_categorical('shader_type', target_type)

def _no_categorical_detected(categorical_type):
  def filter(repo_stats, file_json):
    categorical = file_stats(repo_stats, file_json)[categorical_type]
    return any(cat_value > 0 for cat_value in categorical.values())

  return filter

def new_no_platform():
  return _no_categorical_detected('platforms')

def filter_is_shader(repo_stats, file_json):
  stats = file_stats(repo_stats, file_json)
  return not ("is_shader" in stats and stats['is_shader'])

def new_no_shader_type():
  return _no_categorical_detected('shader_type')

def new_filter_selected_licenses(license_groups, filter_includes = False):
  return (lambda repo_stats, file_json: file_stats(repo_stats, file_json)['license'] in license_groups \
           and ((not filter_includes) or file_stats(repo_stats, file_json)['worst_included_license'] in license_groups))

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




