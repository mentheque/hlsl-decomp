_invalid_answer_limit = 3

# Asks y/n question if optionList not specified, else numerical choice.
# Defaults to -1 on {_invalid_answer_limit} invalid answers
def query(message: str, optionList=None) -> int:
  appendix = "? (y/n)"
  validAnswers = ['y', 'n']
  numberedChoice = optionList is not None

  if numberedChoice:
    validAnswers = [str(x) for x in range(0, len(optionList))]
    appendix = "?\n" + '\n'.join([f"{i}: {option}" for i, option in enumerate(optionList)])

  print('? ' + message + appendix)
  for i in range(_invalid_answer_limit):
    received = input().lower()
    if received in validAnswers:
      if numberedChoice:
        return int(received)
      else:
        return int(received == 'y')
    else:
      print(f"expected {f'0-{len(optionList) - 1}' if numberedChoice else 'y/n'}")
  print(f"Failed to receive valid input.")
  return -1

def invalid_to_no(qresult):
  return 0 if qresult < 0 else qresult

def no_to_invalid(qresult):
  return -1 if qresult == 0 else qresult

def terminate(message : str, code = 1):
  print(message + ". Terminating.")
  exit(code)

def terminate_on_fail(query_result : int, message : str, code = 1):
  if query_result < 0 :
    terminate(message, code)
  return query_result