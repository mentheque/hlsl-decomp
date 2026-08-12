_invalid_answer_limit = 3

# Asks y/n question if optionList not specified, else numerical choice.
# Defaults to 0 on {_invalid_answer_limit} invalid answers
def query(message: str, optionList=None) -> int:
  appendix = "? (y/n)"
  validAnswers = ['y', 'n']
  numberedChoice = optionList is not None

  if numberedChoice:
    validAnswers = [str(x) for x in range(0, len(optionList))]
    appendix = "?\n" + '\n'.join([f"{i}: {option}" for i, option in enumerate(optionList)])

  print(message + appendix)
  for i in range(_invalid_answer_limit):
    received = input().lower()
    if received in validAnswers:
      if numberedChoice:
        return int(received)
      else:
        return int(received == 'y')
    else:
      print(f"expected {f'0-{len(optionList) - 1}' if numberedChoice else 'y/n'}")
  print(f"Failed to receive valid input. Defaulting to {0 if numberedChoice else 'no'}")
  return 0
