# Nesting

With airlock you can nest **scopes** or **policies** arbitrarily.

## Nested Policies

Use `with airlock.policy()` to layer additional policies anywhere in your codebase, all in the same scope's buffer:

```python
with airlock.scope():
    airlock.enqueue(task_a)  

    with airlock.policy(airlock.DropAll()):
        airlock.enqueue(task_b)  

    airlock.enqueue(task_c) 
# `task_a` executes, `task_b` is dropped, `task_c` executes
```

## Nested Scopes

Your `with airlock.scope()` contexts can also be nested. Nested scopes **don't flush independently by default**. They're captured by their parent instead.

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)

    with airlock.scope() as inner:
        airlock.enqueue(task_b)
    # Inner scope exits, but task_b is CAPTURED by outer

# `task_a` and `task_b` both execute here
```

This logic applies recursively; the outermost `airlock.scope` has ultimate authority:

```python
def code_with_side_effects(a):
    with airlock.scope():
        airlock.enqueue(task_c)
        return a * 2

with airlock.scope() as outer:
    airlock.enqueue(task_a)

    with airlock.scope() as inner:
        airlock.enqueue(task_b)
        code_with_side_effects(5)

# `task_a`, `task_b`, and `task_c` all execute here
```

### Wait, what? Why not local control?

If nested scopes were to flush by default, we would have an inverse flywheel -- the more library code adopts airlock, the less control you have. Airlock scopes defined deep in call stacks would recreate the same "side effects might get released anywhere" problem that airlock tries to solve.

With "outermost scope controls", multi-step operations stay well defined even when callees use scopes, without callers needing to know:

```python
def checkout_cart(cart_id):
    with airlock.scope():
        validate_inventory(cart_id)     # May use scopes internally
        charge_payment(cart_id)         # May use scopes internally
        send_confirmation(cart_id)      # May use scopes internally
    # All effects dispatch only if we reach the end successfully
```

### Provenance Tracking

After capturing a nested scope's intents, a parent scope can distinguish its own intents from captured ones:

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)  

    with airlock.scope() as inner:
        airlock.enqueue(task_b) 

    print(f"Own: {len(outer.own_intents)}")          # 1
    print(f"Captured: {len(outer.captured_intents)}")  # 1
    print(f"Total: {len(outer.intents)}")            # 2
```

This enables:
* Auditing where intents came from
* Different handling for own vs captured
* Debugging nested behavior

### The `before_descendant_flushes` Hook

If you want to change this behavior, create your own scope class to define what happens when nested scopes exit.
Whenever a scope exits and is about to flush, this will be called **on each active outer scope in turn** (immediate parent first) 
so all ancestors have a chance to opine. Note that this means `exiting_scope` may not be your immediate child; it might be a great-grandchild or whatever. 

```python
class Scope:
    def before_descendant_flushes(
        self,
        exiting_scope: Scope,
        intents: list[Intent]
    ) -> list[Intent]:
        """
        Called when nested scope exits.

        Return intents to allow through.
        Anything not returned is captured.

        Default: return [] (capture all)
        """
        return []
```

### Use Cases

**Selective capture:**

```python
class SafetyScope(Scope):
    """Capture dangerous tasks, allow others through."""

    def before_descendant_flushes(self, exiting_scope, intents):
        safe = [i for i in intents if not i.dispatch_options.get("dangerous")]
        return safe

with SafetyScope():
    with airlock.scope():
        airlock.enqueue(safe_task)              # Allowed through
        airlock.enqueue(
            dangerous_task,
            _dispatch_options={"dangerous": True}
        )                                        # Captured
    # safe_task executed ✓

# dangerous_task executes here ✓
```

**Independent scopes (opt-out of capture):**

```python
class IndependentScope(Scope):
    """Allow nested scopes to flush independently."""

    def before_descendant_flushes(self, exiting_scope, intents):
        return intents  # Allow all through

with IndependentScope():
    with airlock.scope():
        airlock.enqueue(task)
    # task dispatches here (not captured) ✓
```

