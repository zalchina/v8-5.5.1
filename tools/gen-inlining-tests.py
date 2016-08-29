#!/usr/bin/env python3

# Copyright 2016 the V8 project authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from collections import namedtuple
import textwrap
import sys

SHARD_FILENAME_TEMPLATE = "test/mjsunit/compiler/inline-exception-{shard}.js"
# Generates 2 files. Found by trial and error.
SHARD_SIZE = 94

PREAMBLE = """

// Copyright 2016 the V8 project authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Flags: --allow-natives-syntax --turbo --no-always-opt

// This test file was generated by tools/gen-inlining-tests.py .

// Global variables
var deopt = undefined; // either true or false
var counter = 0;

function resetState() {
  counter = 0;
}

function warmUp(f) {
  try {
    f();
  } catch (ex) {
    // ok
  }
  try {
    f();
  } catch (ex) {
    // ok
  }
}

function resetOptAndAssertResultEquals(expected, f) {
  warmUp(f);
  resetState();
  // %DebugPrint(f);
  eval("'dont optimize this function itself please, but do optimize f'");
  %OptimizeFunctionOnNextCall(f);
  assertEquals(expected, f());
}

function resetOptAndAssertThrowsWith(expected, f) {
  warmUp(f);
  resetState();
  // %DebugPrint(f);
  eval("'dont optimize this function itself please, but do optimize f'");
  %OptimizeFunctionOnNextCall(f);
  try {
    var result = f();
    fail("resetOptAndAssertThrowsWith",
        "exception: " + expected,
        "result: " + result);
  } catch (ex) {
    assertEquals(expected, ex);
  }
}

function increaseAndReturn15() {
  if (deopt) %DeoptimizeFunction(f);
  counter++;
  return 15;
}

function increaseAndThrow42() {
  if (deopt) %DeoptimizeFunction(f);
  counter++;
  throw 42;
}

function returnOrThrow(doReturn) {
  if (doReturn) {
    return increaseAndReturn15();
  } else {
    return increaseAndThrow42();
  }
}

// When passed either {increaseAndReturn15} or {increaseAndThrow42}, it acts
// as the other one.
function invertFunctionCall(f) {
  var result;
  try {
    result = f();
  } catch (ex) {
    return ex - 27;
  }
  throw result + 27;
}

function increaseAndStore15Constructor() {
  if (deopt) %DeoptimizeFunction(f);
  ++counter;
  this.x = 15;
}

function increaseAndThrow42Constructor() {
  if (deopt) %DeoptimizeFunction(f);
  ++counter;
  this.x = 42;
  throw this.x;
}

var magic = {};
Object.defineProperty(magic, 'prop', {
  get: function () {
    if (deopt) %DeoptimizeFunction(f);
    return 15 + 0 * ++counter;
  },

  set: function(x) {
    // argument should be 37
    if (deopt) %DeoptimizeFunction(f);
    counter -= 36 - x; // increments counter
    throw 42;
  }
})

// Generate type feedback.

assertEquals(15, (new increaseAndStore15Constructor()).x);
assertThrowsEquals(function() {
        return (new increaseAndThrow42Constructor()).x;
    },
    42);

function runThisShard() {

""".strip()

def booltuples(n):
  """booltuples(2) yields 4 tuples: (False, False), (False, True),
  (True, False), (True, True)."""

  assert isinstance(n, int)
  if n <= 0:
    yield ()
  else:
    for initial in booltuples(n-1):
      yield initial + (False,)
      yield initial + (True,)

FLAGLETTERS="4321trflcrltfrtld"

def fnname(flags):
    assert len(FLAGLETTERS) == len(flags)

    return "f_" + ''.join(
          FLAGLETTERS[i] if b else '_'
          for (i, b) in enumerate(flags))

NUM_TESTS_PRINTED = 0
NUM_TESTS_IN_SHARD = 0

def printtest(flags):
  """Print a test case. Takes a couple of boolean flags, on which the
  printed Javascript code depends."""

  assert all(isinstance(flag, bool) for flag in flags)

  # The alternative flags are in reverse order so that if we take all possible
  # tuples, ordered lexicographically from false to true, we get first the
  # default, then alternative 1, then 2, etc.
  (
    alternativeFn4,      # use alternative #4 for returning/throwing.
    alternativeFn3,      # use alternative #3 for returning/throwing.
    alternativeFn2,      # use alternative #2 for returning/throwing.
    alternativeFn1,      # use alternative #1 for returning/throwing.
    tryThrows,           # in try block, call throwing function
    tryReturns,          # in try block, call returning function
    tryFirstReturns,     # in try block, returning goes before throwing
    tryResultToLocal,    # in try block, result goes to local variable
    doCatch,             # include catch block
    catchReturns,        # in catch block, return
    catchWithLocal,      # in catch block, modify or return the local variable
    catchThrows,         # in catch block, throw
    doFinally,           # include finally block
    finallyReturns,      # in finally block, return local variable
    finallyThrows,       # in finally block, throw
    endReturnLocal,      # at very end, return variable local
    deopt,               # deopt inside inlined function
  ) = flags

  # BASIC RULES

  # Only one alternative can be applied at any time.
  if alternativeFn1 + alternativeFn2 + alternativeFn3 + alternativeFn4 > 1:
    return

  # In try, return or throw, or both.
  if not (tryReturns or tryThrows): return

  # Either doCatch or doFinally.
  if not doCatch and not doFinally: return

  # Catch flags only make sense when catching
  if not doCatch and (catchReturns or catchWithLocal or catchThrows):
    return

  # Finally flags only make sense when finallying
  if not doFinally and (finallyReturns or finallyThrows):
    return

  # tryFirstReturns is only relevant when both tryReturns and tryThrows are
  # true.
  if tryFirstReturns and not (tryReturns and tryThrows): return

  # From the try and finally block, we can return or throw, but not both.
  if catchReturns and catchThrows: return
  if finallyReturns and finallyThrows: return

  # If at the end we return the local, we need to have touched it.
  if endReturnLocal and not (tryResultToLocal or catchWithLocal): return

  # PRUNING

  anyAlternative = any([alternativeFn1, alternativeFn2, alternativeFn3,
      alternativeFn4])
  rareAlternative = any([alternativeFn1, alternativeFn3, alternativeFn4])

  # If try returns and throws, then don't catchWithLocal, endReturnLocal, or
  # deopt, or do any alternative.
  if (tryReturns and tryThrows and
      (catchWithLocal or endReturnLocal or deopt or anyAlternative)):
    return
  # We don't do any alternative if we do a finally.
  if doFinally and anyAlternative: return
  # We only use the local variable if we do alternative #2.
  if ((tryResultToLocal or catchWithLocal or endReturnLocal) and
      not alternativeFn2):
    return
  # We don't need to test deopting into a finally.
  if doFinally and deopt: return



  # Flag check succeeded.

  trueFlagNames = [name for (name, value) in flags._asdict().items() if value]
  flagsMsgLine = "  // Variant flags: [{}]".format(', '.join(trueFlagNames))
  write(textwrap.fill(flagsMsgLine, subsequent_indent='  //   '))
  write("")

  if not anyAlternative:
    fragments = {
      'increaseAndReturn15': 'increaseAndReturn15()',
      'increaseAndThrow42': 'increaseAndThrow42()',
    }
  elif alternativeFn1:
    fragments = {
      'increaseAndReturn15': 'returnOrThrow(true)',
      'increaseAndThrow42': 'returnOrThrow(false)',
    }
  elif alternativeFn2:
    fragments = {
      'increaseAndReturn15': 'invertFunctionCall(increaseAndThrow42)',
      'increaseAndThrow42': 'invertFunctionCall(increaseAndReturn15)',
    }
  elif alternativeFn3:
    fragments = {
      'increaseAndReturn15': '(new increaseAndStore15Constructor()).x',
      'increaseAndThrow42': '(new increaseAndThrow42Constructor()).x',
    }
  else:
    assert alternativeFn4
    fragments = {
      'increaseAndReturn15': 'magic.prop /* returns 15 */',
      'increaseAndThrow42': '(magic.prop = 37 /* throws 42 */)',
    }

  # As we print code, we also maintain what the result should be. Variable
  # {result} can be one of three things:
  #
  # - None, indicating returning JS null
  # - ("return", n) with n an integer
  # - ("throw", n), with n an integer

  result = None
  # We also maintain what the counter should be at the end.
  # The counter is reset just before f is called.
  counter = 0

  write(    "  f = function {} () {{".format(fnname(flags)))
  write(    "    var local = 3;")
  write(    "    deopt = {};".format("true" if deopt else "false"))
  local = 3
  write(    "    try {")
  write(    "      counter++;")
  counter += 1
  resultTo = "local +=" if tryResultToLocal else "return"
  if tryReturns and not (tryThrows and not tryFirstReturns):
    write(  "      {} {increaseAndReturn15};".format(resultTo, **fragments))
    if result == None:
      counter += 1
      if tryResultToLocal:
        local += 15
      else:
        result = ("return", 15)
  if tryThrows:
    write(  "      {} {increaseAndThrow42};".format(resultTo, **fragments))
    if result == None:
      counter += 1
      result = ("throw", 42)
  if tryReturns and tryThrows and not tryFirstReturns:
    write(  "      {} {increaseAndReturn15};".format(resultTo, **fragments))
    if result == None:
      counter += 1
      if tryResultToLocal:
        local += 15
      else:
        result = ("return", 15)
  write(    "      counter++;")
  if result == None:
    counter += 1

  if doCatch:
    write(  "    } catch (ex) {")
    write(  "      counter++;")
    if isinstance(result, tuple) and result[0] == 'throw':
      counter += 1
    if catchThrows:
      write("      throw 2 + ex;")
      if isinstance(result, tuple) and result[0] == "throw":
        result = ('throw', 2 + result[1])
    elif catchReturns and catchWithLocal:
      write("      return 2 + local;")
      if isinstance(result, tuple) and result[0] == "throw":
        result = ('return', 2 + local)
    elif catchReturns and not catchWithLocal:
      write("      return 2 + ex;");
      if isinstance(result, tuple) and result[0] == "throw":
        result = ('return', 2 + result[1])
    elif catchWithLocal:
      write("      local += ex;");
      if isinstance(result, tuple) and result[0] == "throw":
        local += result[1]
        result = None
        counter += 1
    else:
      if isinstance(result, tuple) and result[0] == "throw":
        result = None
        counter += 1
    write(  "      counter++;")

  if doFinally:
    write(  "    } finally {")
    write(  "      counter++;")
    counter += 1
    if finallyThrows:
      write("      throw 25;")
      result = ('throw', 25)
    elif finallyReturns:
      write("      return 3 + local;")
      result = ('return', 3 + local)
    elif not finallyReturns and not finallyThrows:
      write("      local += 2;")
      local += 2
      counter += 1
    else: assert False # unreachable
    write(  "      counter++;")

  write(    "    }")
  write(    "    counter++;")
  if result == None:
    counter += 1
  if endReturnLocal:
    write(  "    return 5 + local;")
    if result == None:
      result = ('return', 5 + local)
  write(    "  }")

  if result == None:
    write(  "  resetOptAndAssertResultEquals(undefined, f);")
  else:
    tag, value = result
    if tag == "return":
      write(  "  resetOptAndAssertResultEquals({}, f);".format(value))
    else:
      assert tag == "throw"
      write(  "  resetOptAndAssertThrowsWith({}, f);".format(value))

  write(  "  assertEquals({}, counter);".format(counter))
  write(  "")

  global NUM_TESTS_PRINTED, NUM_TESTS_IN_SHARD
  NUM_TESTS_PRINTED += 1
  NUM_TESTS_IN_SHARD += 1

FILE = None # to be initialised to an open file
SHARD_NUM = 1

def write(*args):
  return print(*args, file=FILE)



def rotateshard():
  global FILE, NUM_TESTS_IN_SHARD, SHARD_SIZE
  if MODE != 'shard':
    return
  if FILE != None and NUM_TESTS_IN_SHARD < SHARD_SIZE:
    return
  if FILE != None:
    finishshard()
    assert FILE == None
  FILE = open(SHARD_FILENAME_TEMPLATE.format(shard=SHARD_NUM), 'w')
  write_shard_header()
  NUM_TESTS_IN_SHARD = 0

def finishshard():
  global FILE, SHARD_NUM, MODE
  assert FILE
  write_shard_footer()
  if MODE == 'shard':
    print("Wrote shard {}.".format(SHARD_NUM))
    FILE.close()
    FILE = None
    SHARD_NUM += 1


def write_shard_header():
  if MODE == 'shard':
    write("// Shard {}.".format(SHARD_NUM))
    write("")
  write(PREAMBLE)
  write("")

def write_shard_footer():
  write("}")
  write("%NeverOptimizeFunction(runThisShard);")
  write("")
  write("// {} tests in this shard.".format(NUM_TESTS_IN_SHARD))
  write("// {} tests up to here.".format(NUM_TESTS_PRINTED))
  write("")
  write("runThisShard();")


flagtuple = namedtuple('flagtuple', (
  "alternativeFn4",
  "alternativeFn3",
  "alternativeFn2",
  "alternativeFn1",
  "tryThrows",
  "tryReturns",
  "tryFirstReturns",
  "tryResultToLocal",
  "doCatch",
  "catchReturns",
  "catchWithLocal",
  "catchThrows",
  "doFinally",
  "finallyReturns",
  "finallyThrows",
  "endReturnLocal",
  "deopt"
  ))

emptyflags = flagtuple(*((False,) * len(flagtuple._fields)))
f1 = emptyflags._replace(tryReturns=True, doCatch=True)

# You can test function printtest with f1.

allFlagCombinations = [
    flagtuple(*bools)
    for bools in booltuples(len(flagtuple._fields))
]

if __name__ == '__main__':
  global MODE
  if sys.argv[1:] == []:
    MODE = 'stdout'
    print("// Printing all shards together to stdout.")
    print("")
    write_shard_header()
    FILE = sys.stdout
  elif sys.argv[1:] == ['--shard-and-overwrite']:
    MODE = 'shard'
  else:
    print("Usage:")
    print("")
    print("  python {}".format(sys.argv[0]))
    print("      print all tests to standard output")
    print("  python {} --shard-and-overwrite".format(sys.argv[0]))
    print("      print all tests to {}".format(SHARD_FILENAME_TEMPLATE))

    print("")
    print(sys.argv[1:])
    print("")
    sys.exit(1)

  rotateshard()

  for flags in allFlagCombinations:
    printtest(flags)
    rotateshard()

  finishshard()
