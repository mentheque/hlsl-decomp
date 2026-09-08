from src.utils import compose
from pathlib import Path

class Logger:
  def primary(self, message):
    pass

  def secondary(self, message):
    pass

class NotLogger(Logger):
  pass

class ConsoleLogger(Logger):
  def __init__(self, verbose = True):
    self._verbose = verbose

  def primary(self, message):
    print("!! " + message)

  def secondary(self, message):
    if self._verbose:
      print(message)


class PrefixedLogger(Logger):
  def __init__(self, prefix: str, logger: Logger):
    self._prefix = prefix
    self._logger = logger

  def _compose_prefix(self, f):
    return compose(f, lambda x: self._prefix + " : " + x)

  def primary(self, message):
    self._compose_prefix(self._logger.primary)(message)

  def secondary(self, message):
    self._compose_prefix(self._logger.secondary)(message)

class FileLogger(Logger):
    def __init__(self, filepath, verbose=True):
      self._filepath = filepath
      if self._filepath:
        Path(self._filepath).parent.mkdir(parents=True, exist_ok=True)
      self._verbose = verbose

    def primary(self, message):
      with open(self._filepath, 'a') as f:
        f.write("!! " + message + "\n")

    def secondary(self, message):
      if self._verbose:
        with open(self._filepath, 'a') as f:
          f.write(message + "\n")


class EchoLogger(Logger):
  """Logs messages to both console and file simultaneously"""

  def __init__(self, filepath, console_verbose=True, file_verbose=True):
    self._console_logger = ConsoleLogger(verbose=console_verbose)
    self._file_logger = FileLogger(filepath, verbose=file_verbose)

  def primary(self, message):
    self._console_logger.primary(message)
    self._file_logger.primary(message)

  def secondary(self, message):
    self._console_logger.secondary(message)
    self._file_logger.secondary(message)
