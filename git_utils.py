import os
import shutil
from pathlib import Path
import stat
import subprocess
import re

from config import Config
from utils import Repository

# TODO: check against actual patterns
# Define patterns based on the Licensee gem's FILENAME_REGEXES
_license_filename_patterns = {
    re.compile(r'^(un)?licen[sc]e$', re.IGNORECASE): 1.00,
    re.compile(r'^(un)?licen[sc]e\.(md|markdown|txt|html)$', re.IGNORECASE): 0.95,
    re.compile(r'^copy(ing|right)$', re.IGNORECASE): 0.90,
    re.compile(r'^copy(ing|right)\.(md|markdown|txt|html)$', re.IGNORECASE): 0.85,
    re.compile(r'^(un)?licen[sc]e\.(?!spdx|header)[^.]+$', re.IGNORECASE): 0.80,
    re.compile(r'^copy(ing|right)\.[^./]+$', re.IGNORECASE): 0.75,
    re.compile(r'^(un)?licen[sc]e[-_][^.]*(\.(?!xml|go|gemspec)[^.]+)?$', re.IGNORECASE): 0.70,
    re.compile(r'^copy(ing|right)[-_][^.]*(\.(?!xml|go|gemspec)[^.]+)?$', re.IGNORECASE): 0.65,
    re.compile(r'^\w+[-_](un)?licen[sc]e[^.]*(\.(?!xml|go|gemspec)[^.]+)?$', re.IGNORECASE): 0.60,
    re.compile(r'^\w+[-_]copy(ing|right)[^.]*(\.(?!xml|go|gemspec)[^.]+)?$', re.IGNORECASE): 0.55,
    re.compile(r'^ofl\.(md|markdown|txt|html)$', re.IGNORECASE): 0.50,
    re.compile(r'^ofl\.(?!xml|go|gemspec)[^.]+$', re.IGNORECASE): 0.45,
    re.compile(r'^ofl$', re.IGNORECASE): 0.40,
    re.compile(r'^patents$', re.IGNORECASE): 0.35,
    re.compile(r'^patents\.(?!xml|go|gemspec)[^.]+$', re.IGNORECASE): 0.30,
    re.compile(r'^copying\.lesser$', re.IGNORECASE) : 0.30 # Added by AI
  }

def _git_in_dir(args, repo_dir = None, check = True, capture_output = True, text = True, timeout = 120):
  return subprocess.run(
    ['git'] + (['-C', repo_dir] if repo_dir is not None else []) + args,
    check=check,
    capture_output=capture_output,
    text=text,
    timeout=timeout
  )

def _run_subprocess(config : Config, to_run, error_message : str, handle_error, finally_run = None):
  try:
    return to_run()
  except subprocess.CalledProcessError as e:
    config.log.git.primary(error_message + f": {e}")
    if hasattr(e, 'stderr') and e.stderr:
      config.log.git.primary(f"Error output: {e.stderr}")

    handle_error(e)
  finally:
    if finally_run is not None :
      finally_run()

def _raise(e):
  raise e

def _clone_empty(config: Config, repo : Repository) -> Path:
  config.log.git.primary(f"Setting up empty clone of {repo.name} in {config.git_directory}")

  url = repo.clone_url
  if config.github_token:
    if url.startswith("https://"):
      url = url.replace("https://", f"https://{config.github_token}@")

  target_dir = repo_dir(config, repo)

  def remove_readonly(func, path, _):
    """Clear the readonly bit and reattempt the operation"""
    os.chmod(path, stat.S_IWRITE)
    func(path)

  if os.path.exists(target_dir):
    shutil.rmtree(target_dir, onerror=remove_readonly)

  _run_subprocess(
    config,
    lambda : _git_in_dir(['clone', '--filter=blob:none', '--no-checkout', '--depth', '1',
       '--branch', repo.default_branch, url, target_dir]), # no dir specified
    "Clone failed",
    _raise
  )

  return target_dir


def _get_filenames_related_to_licenses(config : Config, repo : Repository, repo_dir : Path):
  def inner():
    result = _git_in_dir(['ls-tree', '-r', repo.default_branch, '--name-only'], repo_dir, timeout=300)

    def is_license_named_file(file):
      basename = os.path.basename(file)
      return any(pattern.match(basename) for pattern in _license_filename_patterns.keys())

    all_files = result.stdout.strip().split('\n')
    matched_files = [file for file in all_files if file and is_license_named_file(file)]

    return matched_files

  return _run_subprocess(
    config,
    inner,
    "Getting file list failed",
    _raise
  )

def _setup_sparse_checkout(config : Config, repo : Repository, repo_dir : Path, rules : [str]):
  def inner():
    # Set up sparse checkout
    _git_in_dir(['sparse-checkout', 'init', '--no-cone'], repo_dir, timeout=100)
    _git_in_dir(['sparse-checkout', 'set', '--no-cone'], repo_dir)

    total_rules = rules + ["*." + ext for ext in config.file_extensions]

    for rule in total_rules: #rules:
      _git_in_dir(['sparse-checkout', 'add', rule], repo_dir)

  return _run_subprocess(
    config,
    inner,
    "Setting up sparse-checkout rules failed",
    _raise
  )

def _checkout(config : Config, repo : Repository, repo_dir = None):
  def with_ntfs():
    _git_in_dir(['checkout', repo.default_branch], repo_dir)  # text = False?

  def without_ntfs(e):
    def inner():
      _git_in_dir(['config', 'core.protectNTFS', 'false'], repo_dir)
      _git_in_dir(['checkout', repo.default_branch], repo_dir)

    return _run_subprocess(
      config,
      inner,
      "Checkout failed with protectNTFS off",
      _raise,
      finally_run= (lambda : _git_in_dir(['config', 'core.protectNTFS', 'true'], repo_dir))
    )

  return _run_subprocess(
    config,
    with_ntfs,
    "Checkout failed",
    without_ntfs
  )

def clone_license_named_and_target_files(config : Config, repo : Repository):
  config.log.git.primary(f"Starting sparse clone of {repo.name}")
  repo_dir = _clone_empty(config, repo)
  _setup_sparse_checkout(
    config,
    repo,
    repo_dir,
    _get_filenames_related_to_licenses(config, repo, repo_dir)
  )
  _checkout(config, repo, repo_dir)

from utils import join_path

def repo_dir(config : Config, repo : Repository):
  return join_path(config.git_directory, repo.full_name)



