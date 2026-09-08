
from github import Github, Auth
from pathlib import Path
import json
from datetime import datetime
from calendar import monthrange
from src.utils import Repository

from src.config import Config


def _init_github(config : Config) -> Github:
  if config.github_token is None:
    config.log.github.primary("Missing authentication token (reduced limits)")

  auth = Auth.Token(config.github_token) if config.github_token else None
  return Github(auth=auth) if auth else Github()


def _to_list(config : Config, paginated_list):
  config.log.github.secondary(f"Found {paginated_list.totalCount} repositories")
  return [(repo.name, repo.full_name, repo.clone_url, repo.blobs_url, repo.default_branch) for repo in paginated_list]

 # TODO: error handling
def _dump(dump_path : Path, results):
  dump_path.parent.mkdir(exist_ok=True, parents=True)

  with open(dump_path, "w") as rl_file:
    json.dump(results, rl_file)

  return results


def _exhaust_request(config : Config, query : str):
  MAX_PER_REQUEST = 1000

  def maxed_out(results):
    return results.totalCount >= MAX_PER_REQUEST

  gh = _init_github(config)

  def request(year=None, month=None, day=None):
    def request_inner(pushed_filter):
      return gh.search_repositories(query=query + f" pushed:" + pushed_filter,
                                    sort="updated", order="desc")

    def daytoday_range(date1: datetime, date2: datetime):
      return f"{date1.date()}..{date2.date()}"

    if day is not None:
      return request_inner(datetime(year=year, month=month, day=day).date())
    if month is not None:
      return request_inner(daytoday_range(datetime(year=year, month=month, day=1),
                                          datetime(year=year, month=month, day=monthrange(year, month)[1])))
    if year is not None:
      return request_inner(daytoday_range(datetime(year=year, month=1, day=1),
                                          datetime(year=year, month=12, day=31)))
    return request_inner(daytoday_range(datetime(year=2008, month=1, day=1), datetime.now()))

  results = []

  # TODO: fix copypaste
  for year in range(datetime.now().year, 2007, -1):
    config.log.github.secondary(f"Search: year {year}")

    years_results = request(year)
    if maxed_out(years_results):
      for month in range(12, 0, -1):
        config.log.github.secondary(f"Search: month {month}")

        months_results = request(year, month)
        if maxed_out(months_results):
          for day in range(monthrange(year, month)[1], 0, -1):
            config.log.github.secondary(f"Search: day {day}")

            days_results = request(year, month, day)
            if maxed_out(days_results):
              config.log.github.secondary(f"{MAX_PER_REQUEST} \
                or more results for {datetime(year=year, month=month, day=day).date()}, some may be unaccounted for. \
                This is as far granular as API goes, may need to consider other methods.")
            results += _to_list(config, days_results)
        else:
          results += _to_list(config, months_results)
    else:
      results += _to_list(config, years_results)

  config.log.github.primary(f"Found {len(results)} repositories in total")
  return results

def _exhaust_resquests_join(config : Config, queries : [str], log_messages : [str]):
  results = []
  for query, message in zip(queries, log_messages):
    config.log.github.secondary(message)
    results += _exhaust_request(config, query)
  return results

def _language_query(config : Config) -> str:
  return f"language:{config.language}"

# TODO : fix copypaste
def gh_full_repository_list(config : Config):
  config.log.github.primary("Fetching full repository list")
  return _raw_list_to_pclass(
    _dump(
      _full_rlist_path(config),
      _exhaust_request(
        config,
        _language_query(config)
      )
    )
  )

#TODO : fix logs
from src.config import LicenseType
def gh_selected_licenses(config : Config, licenses : [LicenseType] = None, file_path = None):
  if licenses is None:
    licenses = config.licenses

  if file_path is None:
    file_path = _selected_licenses_rlist_path(config)

  base_query = _language_query(config)
  queries = [base_query + f" license:{license_type.gh_search_name}" for license_type in licenses]
  messages = [f"Fetching licenses with {license_type.name} license" for license_type in licenses]

  return _raw_list_to_pclass(
    _dump(
      file_path,
      _exhaust_resquests_join(
        config,
        queries,
        messages
      )
    )
  )


def gh_top_stars(config : Config):
  config.log.github.primary("Fetching list of top starred repositories")
  return _raw_list_to_pclass(
    _dump(
      _top_starred_rlist_path(config),
      _to_list(
        config,
        _init_github(config).search_repositories(
          query=_language_query(config),
          sort="stars",
          order="desc"
        )
      )
    )
  )


def _raw_list_to_pclass(raw):
  return [Repository(*tple) for tple in raw]

# TODO: error handling
def _load(filename):
  with open(filename, "r") as rl_file:
    return _raw_list_to_pclass(json.load(rl_file))

def load_full_rlist(config: Config):
  return _load(_full_rlist_path(config))

def load_top_starred_rlist(config : Config):
  return _load(_top_starred_rlist_path(config))

def load_selected_licenses_rlist(config : Config, file_path = None):
  return _load(_selected_licenses_rlist_path(config) if file_path is None else file_path)


from src.utils import join_path
def _dump_file_path(config : Config, filename):
  return join_path(config.repository_list_dir, filename)

def _full_rlist_path(config : Config):
  return _dump_file_path(config, 'repository_list.json')

def _top_starred_rlist_path(config : Config):
  return _dump_file_path(config, 'top_starred_list.json')

def _selected_licenses_rlist_path(config : Config):
  return _dump_file_path(config, 'selected_licenses_list.json')

from enum import Enum
class RepositoryLists(Enum):
  Full = 1
  TopStarred = 2
  SelectedLicenses = 3

_loaders = {
  RepositoryLists.Full : load_full_rlist,
  RepositoryLists.TopStarred : load_top_starred_rlist,
  RepositoryLists.SelectedLicenses : load_selected_licenses_rlist
}

_gh_getters = {
  RepositoryLists.Full: gh_full_repository_list,
  RepositoryLists.TopStarred: gh_top_stars,
  RepositoryLists.SelectedLicenses: gh_selected_licenses
}

def load(config : Config, rlist : RepositoryLists):
  return _loaders[rlist](config)

def gh_get(config : Config, rlist : RepositoryLists):
  return _gh_getters[rlist](config)