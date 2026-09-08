import os.path
from pathlib import Path
import json
import tempfile
import subprocess

from src.config import Config
from src.utils import Repository, join_path

def _run_scancode(config : Config, repo_dir : Path, save_to = None):
  if save_to is None:
    with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False
    ) as temp_json:
      output_file = temp_json.name
  else:
    Path(save_to).parent.mkdir(parents=True, exist_ok=True)
    output_file = save_to

  command = [
    "scancode",
    "--license",
    "--json-pp",
    output_file,
    "--processes", str(config.scancode_processes),
    "--classify",
    repo_dir,
  ]

  try:
    config.log.licenses.primary(f"Scanning {repo_dir} with ScanCode Toolkit...")

    result = subprocess.run(
      command, text=True, check=True
    )

    config.log.licenses.primary("Scan completed successfully!")

    # Read and parse the generated JSON file
    with open(output_file, "r", encoding="utf-8") as f:
      scan_data = json.load(f)

    return scan_data

  except subprocess.CalledProcessError as e:
    config.log.licenses.primary(f"ScanCode execution failed with exit code {e.returncode}")
    config.log.licenses.secondary(f"Error output:\n{e.stderr}")
    raise

  finally:
    # Clean up the temporary JSON file from disk
    if save_to is None and Path(output_file).exists():
      Path(output_file).unlink()

def scancode_and_cache(config : Config, repo : Repository):
  config.log.licenses.primary(f"Scanning {repo.name}")
  return _run_scancode(config, repo_dir(config, repo), scancode_cache_filename(config, repo))

def load_scancode(config : Config, repo : Repository):
  filename = scancode_cache_filename(config, repo)
  if not Path(filename).exists():
    config.log.licenses.primary(f"Scancode for {repo.name} has not been generated")
    return None

  with open(filename, "r", encoding="utf-8") as f:
    return json.load(f)

def scancode_cache_filename(config: Config, repo : Repository):
  return join_path(config.scancode_cache_dir, repo.full_name.replace("/", "_") + ".json")

def _walk_repo(config : Config, repo : Repository):
  config.log.licenses.primary(f"Establishing license hierarchy in {repo.name}")
  scancode = load_scancode(config, repo)

  shaders = []

  licenses_by_dir = {}
  def find_closest_licenses(dir):
    if dir in licenses_by_dir:
      return licenses_by_dir[dir]

    best_match = None
    best_match_len = 0
    for licensehaving_dir in licenses_by_dir.keys():
      if dir.startswith(licensehaving_dir):
        clen = len(licensehaving_dir)
        if clen >= best_match_len:
          best_match = licensehaving_dir
          best_match_len = clen

    ret = []
    if best_match is not None:
      ret = licenses_by_dir[best_match]

    # Caching
    licenses_by_dir[dir] = ret
    return ret

  for file in scancode['files']:
    if file["is_legal"]:
      current_dir = os.path.dirname(file["path"])
      if current_dir not in licenses_by_dir:
        licenses_by_dir[current_dir] = []
      licenses_by_dir[current_dir].append(file)

  for file in scancode['files']:
    if file["type"] == "file":
      # Includes may not all be shader files, so best not to filter for that here.
      #if is_shader(file["path"]):
      applicable_licenses = find_closest_licenses(os.path.dirname(file["path"]))
      if file["detected_license_expression"] is not None:
        applicable_licenses = [file]

      shaders.append((file, applicable_licenses))

  return shaders

def _walk_repos(config : Config, repos : [Repository]):
  config.log.licenses.primary(f"Starting license search for list of {len(repos)} repositories")
  walked = []
  failed = []
  for repo in repos:
    try:
      walked_repo = _walk_repo(config, repo)
      if len(walked_repo) > 0:
        walked.append((repo, walked_repo))
    except Exception as e:
      config.log.licenses.secondary(f"Failed to work out licenses for {repo.name}")
      config.log.licenses.secondary(str(e))
      failed.append(repo)

  config.log.licenses.primary(f"License search complete, successful {len(repos) - len(failed)}, failed {len(failed)}")

  return walked, failed

# Leave only shaders where relevant license(s) can be traced to a single file
def _filter_file_conclusive(walked, store_empty_repos = False):
  conclusive = []
  for repo, walked_repo in walked:
    conclusive_repo = [(filenlicenses[0], filenlicenses[1][0])
                       for filenlicenses in walked_repo if len(filenlicenses[1]) == 1]
    if len(conclusive_repo) > 0 or store_empty_repos:
      conclusive.append((repo, conclusive_repo))
  return conclusive

from src.config import LicenseGroup

def _sort_file_conclusive(config : Config, file_conclusive, store_empty_repos = False):
  permissive_prefixes = [license.unique_prefix for license in config.licenses
                         if license.group == LicenseGroup.Permissive]
  gpl_prefixes = [license.unique_prefix for license in config.licenses
                         if license.group == LicenseGroup.GPL]

  def clearly_in_group(fconc, group_prefixes):
    return fconc[1]["detected_license_expression_spdx"] is not None \
           and len(fconc[1]["detected_license_expression_spdx"].split(" ")) == 1 \
           and any(fconc[1]["detected_license_expression_spdx"].startswith(pref)
                   for pref in group_prefixes)

  def clearly_permissive(fconc):
    return clearly_in_group(fconc, permissive_prefixes)

  def clearly_gpl(fconc):
    return clearly_in_group(fconc, gpl_prefixes)

  def detected_none(fconc):
    return fconc[1]["detected_license_expression_spdx"] is None

  clear_permissive = []
  clear_gpl = []
  failed_to_detect_any = []
  non_permissive_or_unclear = []

  for repo, conclusive_repo in file_conclusive:
    clear_permissive_repo = []
    clear_gpl_repo = []
    failed_to_detect_any_repo = []
    non_permissive_or_unclear_repo = []
    for fconc in conclusive_repo:
      if clearly_permissive(fconc):
        clear_permissive_repo.append(fconc)
      elif clearly_gpl(fconc):
        clear_gpl_repo.append(fconc)
      elif detected_none(fconc):
        failed_to_detect_any_repo.append(fconc)
      else:
        non_permissive_or_unclear_repo.append(fconc)

    for glob, loc in [(clear_permissive, clear_permissive_repo)
      , (clear_gpl, clear_gpl_repo)
      , (failed_to_detect_any, failed_to_detect_any_repo)
      , (non_permissive_or_unclear, non_permissive_or_unclear_repo)]:
      if len(loc) > 0 or store_empty_repos:
        glob.append((repo, loc))

  return clear_permissive, clear_gpl, failed_to_detect_any, non_permissive_or_unclear

# from [(repo, [(file, license)])] to [(file, license)]
def flatten_removing_repos(list_w_repos):
  return [shader for _, repo_shaders in list_w_repos for shader in repo_shaders]


from src.git_utils import repo_dir
def file_path(config : Config, repo : Repository, file_json):
  return repo_dir(config, repo) / Path(*Path(file_json["path"]).parts[1:])

def file_path_fstat(config : Config, repo : Repository, file_stat):
  return repo_dir(config, repo) / Path(*Path(file_stat["case_sensitive_path"]).parts[1:])