# litedict

> Dictionary implemented on top of SQLite

## Why?

You can use this to implement a persistent dictionary. It also uses some SQLite syntax to enable getting keys using pattern matching (see examples).

## Installation

```
pip install litedict
```

## Alternatives

* [RaRe-Technologies/sqlitedict](https://github.com/RaRe-Technologies/sqlitedict): This library uses a separate writing thread. Modern versions of SQLite are thread safe by default (serialized), so a separate writing thread is not strictly needed. It can be helpful to avoid DB locks, but it also adds extra complexity. That implementation is also missing some performance optimizations that are present in this repository.

## Examples

The examples are taken from the tests in [`tests.ipynb`](./tests.ipynb)


```python
from litedict import SQLDict

TEST_1 = "key_test_1"
TEST_2 = "key_test_2"
```

Basic functionality


```python
d = SQLDict(":memory:")

d[TEST_1] = "asdfoobar"

assert d[TEST_1] == "asdfoobar"

del d[TEST_1]

assert d.get(TEST_1, None) is None

# execute multiple instructions inside a transaction
with d.transaction():
    d["asd"] = "efg"
    d["foo"] = "bar"
```

Glob matching


```python
d[TEST_1] = "asdfoobar"

d[TEST_2] = "foobarasd"

d["key_testx_3"] = "barasdfoo"

assert d.glob("key_test*") == ["asdfoobar", "foobarasd", "barasdfoo"]

assert d.glob("key_test_?") == ["asdfoobar", "foobarasd"]

assert d.glob("key_tes[tx]*") == ["asdfoobar", "foobarasd", "barasdfoo"]
```

Numbers


```python
d[TEST_1] = 1

d[TEST_2] = 2

assert d[TEST_1] + d[TEST_2] == 3
```

## Benchmarks


```python
from string import ascii_lowercase, printable
from random import choice
import random


def random_string(string_length=10, fuzz=False, space=False):
    """Generate a random string of fixed length """
    letters = ascii_lowercase
    letters = letters + " " if space else letters
    if fuzz:
        letters = printable
    return "".join(choice(letters) for i in range(string_length))
```


```python
import gc

import pickle

import json
```

**Pickle**


```python
d = SQLDict(
    ":memory:",
    encoder=lambda x: pickle.dumps(x).hex(),
    decoder=lambda x: pickle.loads(bytes.fromhex(x)),
)

gc.collect()

# %%timeit -n20000 -r10

d[random_string(8)] = random_string(50)

d.get(random_string(8), None)

# 69.2 µs ± 4.84 µs per loop (mean ± std. dev. of 10 runs, 20000 loops each)
```

**Noop**

```python
d = SQLDict(
    ":memory:",
    encoder=lambda x: x,
    decoder=lambda x: x,
)

gc.collect()

# %%timeit -n20000 -r10

d[random_string(8)] = random_string(50)

d.get(random_string(8), None)

# 66.8 µs ± 2.41 µs per loop (mean ± std. dev. of 10 runs, 20000 loops each)
```

**JSON**

```python
d = SQLDict(
    ":memory:",
    encoder=lambda x: json.dumps(x),
    decoder=lambda x: json.loads(x),
)

gc.collect()

# %%timeit -n20000 -r10

d[random_string(8)] = random_string(50)

d.get(random_string(8), None)

# 68.6 µs ± 3.07 µs per loop (mean ± std. dev. of 10 runs, 20000 loops each)
```

**Pickle Python obj**


```python
d = SQLDict(
    ":memory:",
    encoder=lambda x: pickle.dumps(x).hex(),
    decoder=lambda x: pickle.loads(bytes.fromhex(x)),
)

gc.collect()

class C:
    def __init__(self, x):
        self.x = x

    def pp(self):
        return x

    def f(self):
        def _f(y):
            return y * self.x ** 2

        return _f

# %%timeit -n20000 -r10

d[random_string(8)] = C(random.randint(1, 200))

d.get(random_string(8), None)

# 41.1 µs ± 2.75 µs per loop (mean ± std. dev. of 10 runs, 20000 loops each)
```


**Dictionary**


```python
d = {}

gc.collect()

# %%timeit -n20000 -r10

d[random_string(8)] = random_string(50)

d.get(random_string(8), None)

# 53.1 µs ± 4.42 µs per loop (mean ± std. dev. of 10 runs, 20000 loops each)
```

## Writeback Cache

Inspired by the writeback cache of [shelve](https://docs.python.org/3/library/shelve.html), litedict optionally implements a writeback cache (defaults to False). This enables mutating mutable objects by keeping a cache of all entries accessed and writing them back upon `d.close()` or `d.sync()`. 

Consider the following examples:

This will *not* save the values mutated:

```python
d = SQLDict("example.db",writeback=False)
d['mylist'] = []
d['mylist'].append('myitem')
print(d['mylist']) # output: []
```

This *will* mutate the item and then save it upon `d.close()` to be read again

```python
d = SQLDict("example.db",writeback=True)
d['mylist'] = []
d['mylist'].append('myitem')
print(d['mylist']) # output: ['myitem']

d.close()

d = SQLDict("example.db",writeback=True)
print(d['mylist']) # output: ['myitem']
```

Finally, to achieve the save thing without `writeback=True` you could do the following:

```python
d = SQLDict("example.db",writeback=False)
d['mylist'] = []

mylist = d['mylist']
mylist.append('myitem')

d['mylist'] =  mylist # This saves the item
print(d['mylist']) # output: ['myitem']

# Good practice is to call d.close() but it is commented out
# to demonstrate that you don't even need it since it is written above

d2 = SQLDict("example.db",writeback=True)
print(d2['mylist']) # output: ['myitem']
```



## Changelog

* 0.3
	* Add transactions as part of the dictionary 


## Meta


Ricardo Ander-Egg Aguilar – [@ricardoanderegg](https://twitter.com/ricardoanderegg) –

- [ricardoanderegg.com](http://ricardoanderegg.com/)
- [github.com/polyrand](https://github.com/polyrand/)
- [linkedin.com/in/ricardoanderegg](http://linkedin.com/in/ricardoanderegg)

Distributed under the MIT license. See ``LICENSE`` for more information.

## Contributing

The only hard rules for the project are:

* No extra dependencies allowed
* No extra files, everything must be inside the main module's `.py` file.
* Tests must be inside the `tests.ipynb` notebook.