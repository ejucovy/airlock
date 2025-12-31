# airlock

Express side effects anywhere. Control whether & when they escape.

## The idea

```python
import airlock

class Order:
    def process(self):
        self.status = "processed"
        self.save()
        airlock.enqueue(notify_warehouse, self.id)
        airlock.enqueue(send_confirmation_email, self.id)
```

The **execution context** decides when (and whether) your side effects actually get dispatched:

```python
# HTTP endpoint: flush at end of request
with airlock.scope():
    order.process()
# side effects dispatch here

# Migration script: suppress everything
with airlock.scope(policy=airlock.DropAll()):
    order.process()
# nothing dispatched

# Test: fail if anything tries to escape
with airlock.scope(policy=airlock.AssertNoEffects()):
    test_pure_logic()
# raises if any enqueue() called

# Admin-facing HTTP endpoint: flush at end of request with selective filtering
with airlock.scope(policy=airlock.BlockTasks({"send_confirmation_email"}):
    order.process()
# warehouse gets notified, customer doesn't get emailed
```

(If you're using Django, you can ignore `with airlock.scope()` -- it'll hook in where you expect. More on this below.)

## The pattern this enables

Side effects at a convergent point deep in a call stack -- like model methods -- are dangerous:

```python
class Order:
    def process(self):
        self.status = "processed"
        self.save()
        notify_warehouse.delay(self.id)
        send_confirmation_email(self.id)
```

But *why* are they dangerous?

- **You can't opt out.** Every `Order.objects.create()`, fixture load, and migration that touches orders fires the task.
- **It's invisible at the call site.** `order.status = "shipped"; order.save()` looks innocent. You have to know to check `save()` for side effects.
- **Testing is miserable.** Mock at the task level (fragile), run a real broker (slow), or `CELERY_ALWAYS_EAGER=True` (hides async bugs).
- **Bulk operations explode.** A loop calling `save()` on 10,000 orders enqueues 10,000 tasks.
- **Re-entrancy bites.** `User.save()` calls `enrich_from_api.delay(user.id)`. That task fetches data, sets `user.age` and `user.income`, then calls `user.save()`... which enqueues `enrich_from_api` again. Now you're adding flags like `_skip_enrich=True` and threading them through everywhere. (Or you're diffing against `Model.objects.get(pk=self.pk)` in every `save()` and using `save(changed_fields=[])` as a task dispatcher. Now you have three problems.)

The problem isn't *where* the intent is expressed. It's that **the effects are silent, and escape immediately**.

With airlock, it doesn't:

```python
import airlock

class Order:
    def process(self):
        self.status = "processed"
        self.save()
        airlock.enqueue(notify_warehouse, self.id)        # buffered for later
        airlock.enqueue(send_confirmation_email, self.id) # buffered for later
```

Now `save()` is a *legitimate* place to express domain intent:

- **Colocation.** The model knows when it needs side effects. That knowledge sometimes belongs here.
- **DRY.** Every code path that saves an Order gets the side effects. You can't forget.
- **Control.** The *scope* decides what escapes, not the call site.
- **Visibility.** You can inspect the buffer before it flushes, run a model method and compare before-and-after... great for tests!
- **Control again.** Define your own nested scopes for surgically stacked policies, or even define multiple execution boundaries.

Hidden control flow becomes explicit. Side effects can be defined close to the source, and still escape in one place.

## What this unlocks

Without airlock, "enqueue side effects at the edge" is an important constraint for maintaining predictable timing, auditability, and control. Side effects deep in the call stack are dangerous, so you're forced to hoist them.

With airlock, both patterns are safe:

- **Edge-only**: All enqueues in views/handlers. Explicit, visible at the boundary.
- **Colocated**: Enqueues near domain logic (`save()`, signals, service methods). DRY, encapsulated.

Choose based on your team's preferences, not out of necessity. See [When you don't need this](#when-you-dont-need-this) for more on picking your style.

## Integration-aware default boundaries

When you use the Django and Celery integrations, effects escape by default where you would expect:

| Context | When | Dispatch if | Discard if |
|---------|------|-------------|------------|
| **HTTP request** | End of request, deferred to `on_commit` | 1xx/2xx/3xx response | 4xx/5xx or exception |
| **Management command** | End of `handle()` | Normal exit | Exception (or `--dry-run`) |
| **Celery task** | End of task | Success | Exception |

Each integration provides sensible defaults. Override with policies or custom scope classes. Or use the lower-level `with airlock.scope()` API to control behaviors explicitly in your own code.

## Alternatives

### `transaction.on_commit()`

In many Django projects, the typical pattern evolution is to start with immediately-escaping tasks:

```python
class Order:
    def process(self):
        self.status = "processed"
        self.save()
        notify_warehouse.delay(self.id)
        send_confirmation_email(self.id)
```

And then migrate to a transaction boundary:

```python
class Order:
    def process(self):
        self.status = "processed"
        self.save()
        transaction.on_commit(lambda: notify_warehouse.delay(self.id))
        transaction.on_commit(lambda: send_confirmation_email(self.id))
```

This solves one problem: don't fire if the transaction rolls back, and don't fire until database state has settled. But it doesn't solve the rest:

- **Only works inside a transaction.** If you call `on_commit()` while there isn't an open transaction, the callback will be executed immediately. So the temporal sequence of your code changes silently based on both global configuration (`ATOMIC_REQUESTS`) and any given call stack (`with transaction.atomic()`) -- yikes!
- **No opt-out.** Migrations, fixtures, tests still trigger.
- **No introspection.** Can't ask "what's about to fire?"
- **No policy control.** Can't suppress specific tasks or block regions.
- **What about sequential transactions? What about savepoints (nested transactions)?** Hard to reason about! (Your side effects will run after each outermost transaction commits, in the order they were registered within that transaction's scope.)

Airlock gives you `on_commit` behavior (via `DjangoScope`) *plus* policies, introspection, and a single dispatch boundary.

### Django signals

Signals move *where* the side effect lives, not *whether* or *when* it fires. This is a powerful tool for code organization, but it doesn't address the core problems.

### Celery chords/chains

If your tasks trigger other tasks, consider whether the workflow should be defined upfront instead. `chain(task_a.s(), task_b.s())` makes the cascade explicit with no hidden enqueues.

Airlock helps when that's not practical: triggers deep in the call stack that can't be hoisted trivially, dynamic cascades, tasks that conditionally trigger others, or legacy code where tasks already enqueue tasks.

## When you don't need this

You might not need airlock if:

- **Views are the only place you enqueue.** All `.delay()` calls (or `on_commit(lambda: task.delay(...))`) are in views, never in models or reusable services.
- **Tasks don't chain.** No task triggers another task within its code.
- **You use `ATOMIC_REQUESTS`.** Transaction boundaries are already request-scoped, so `on_commit` behaves predictably.
- **You're happy with these constraints.** You accept that domain intent ("notify warehouse when order ships") lives in views, not models.

In this scenario, the view plus the database transaction *is* your boundary.

That's a valid architecture. (I prefer it actually!) Airlock is for when you *want* to express intent closer to the domain -- in `save()`, in signals, in service methods -- without losing control over escape. See [What this unlocks](#what-this-unlocks) for how airlock makes this a choice rather than a constraint.

## Installation

```bash
pip install airlock
```

## Basic usage

```python
import airlock

from my_app.tasks import send_email, sync_to_warehouse

# 1. Domain code expresses intent (no .delay() calls)
def do_business_logic():
    # ...
    airlock.enqueue(send_email, user_id=123)
    airlock.enqueue(sync_to_warehouse, item_id=456)

# 2. Scope controls what escapes
with airlock.scope():
    do_business_logic()
# side effects dispatch when scope exits
```

## Policies

Control what escapes:

```python
# Allow everything (default)
airlock.scope(policy=airlock.AllowAll())

# Drop everything silently
airlock.scope(policy=airlock.DropAll())

# Raise if anything is enqueued
airlock.scope(policy=airlock.AssertNoEffects())

# Block specific tasks by name
airlock.scope(policy=airlock.BlockTasks({"myapp.tasks:send_sms"}))

# Log everything at flush time
airlock.scope(policy=airlock.LogOnFlush())

# Combine policies
airlock.scope(policy=airlock.CompositePolicy(
    airlock.LogOnFlush(),
    airlock.BlockTasks({"myapp.tasks:expensive_rebuild"}),
))
```

## Local policy contexts

Sometimes you need policy control over a *region* of code without creating a separate buffer. Use `airlock.policy()`:

```python

def do_business_logic():
    # ...
    airlock.enqueue(task_b)
    airlock.enqueue(task_c)

with airlock.scope():
    airlock.enqueue(task_a)

    with airlock.policy(airlock.DropAll()):
        do_business_logic()

    airlock.enqueue(task_d)

# when scope exits, task_a and task_d will dispatch, task_b and task_c won't
```

All four intents go to the **same buffer**. The policy is captured on each intent at enqueue time and applied at flush.

This differs from nested scopes, which create separate buffers with independent flush/discard lifecycles.

### Use cases

**Suppress effects in read-only operations:**

```python
def view_order(request, order_id):
    order = Order.objects.get(id=order_id)

    with airlock.policy(airlock.DropAll()):
        # Reuse business logic but suppress any side effects
        summary = generate_order_summary(order)

    return render(request, "order.html", {"summary": summary})
```

**Block specific tasks in a region:**

```python
def backfill_orders(orders):
    for order in orders:
        with airlock.policy(airlock.BlockTasks({"myapp.tasks:send_email"})):
            # Process normally but don't spam customers
            process_order(order)
```

**Nested policies stack (innermost runs first):**

```python
with airlock.policy(LogOnFlush()):
    with airlock.policy(BlockTasks({"notifications"})):
        airlock.enqueue(send_notification)  # blocked, then logged
```

## Introspection

The buffer contains everything attempted, regardless of policy:

```python
with airlock.scope() as s:
    airlock.enqueue(task_a)

    with airlock.policy(airlock.DropAll()):
        airlock.enqueue(task_b)

    # s.intents contains both in enqueue order - complete audit log
    assert len(s.intents) == 2

    intent_a, intent_b = s.intents  # Ordered by enqueue time

    # task_a has no local policies, will dispatch
    assert intent_a.local_policies == ()
    assert intent_a.passes_local_policies() is True

    # task_b captured DropAll, won't dispatch
    assert len(intent_b.local_policies) == 1
    assert isinstance(intent_b.local_policies[0], airlock.DropAll)
    assert intent_b.passes_local_policies() is False
# When scope exits, only task_a dispatches
```

### Dispatch semantics: three layers of decision

Whether an intent actually executes depends on three independent layers:

| Layer | Question | Evaluated by |
|-------|----------|--------------|
| **Intent** | Does this intent pass its local policies? | `intent.passes_local_policies()` |
| **Scope** | Will this scope flush or discard? | Scope lifecycle |
| **Dispatch** | Does execution succeed? | `_execute()` / dispatcher |

`passes_local_policies()` only answers the first question. It does not consider scope-level policy, whether the scope flushes, or dispatch success.

### Inspecting buffered intents

```python
with airlock.scope() as s:
    do_stuff()

    # See what's buffered before it escapes
    for intent in s.intents:
        print(f"{intent.name}: {intent.args}, {intent.kwargs}")
```

## Dispatch options

Pass queue-specific options via `_dispatch_options`. Options are passed directly to the underlying dispatch method:

```python
# With celery_executor
airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={"countdown": 60, "queue": "emails"},
)
# Calls: task.apply_async(args=(user_id,), kwargs={}, countdown=60, queue="emails")

# With django_q_executor
airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={"group": "emails", "timeout": 60},
)
# Calls: async_task(send_email, user_id=123, group="emails", timeout=60)
```

Options are specific to your executor - use Celery options with `celery_executor`, django-q options with `django_q_executor`, etc. For plain callables, `_dispatch_options` is silently ignored.

## How dispatch works

Dispatch is handled by **executors** — pluggable functions that execute intents. The default executor runs tasks synchronously.

**Built-in executors:**

```python
from airlock.integrations.executors.sync import sync_executor          # Default: task(*args, **kwargs)
from airlock.integrations.executors.celery import celery_executor      # Celery: task.delay() or task.apply_async()
from airlock.integrations.executors.django_q import django_q_executor  # django-q: async_task(task, *args, **kwargs)
from airlock.integrations.executors.huey import huey_executor          # Huey: task.schedule()
from airlock.integrations.executors.dramatiq import dramatiq_executor  # Dramatiq: task.send() or task.send_with_options()
```

**Celery executor** checks for `.delay()` / `.apply_async()` and falls back to sync:

```python
with airlock.scope(executor=celery_executor):
    airlock.enqueue(celery_task, ...)    # Dispatches via .delay()
    airlock.enqueue(plain_function, ...) # Falls back to sync
```

**django-q executor** always uses `async_task()`:

```python
with airlock.scope(executor=django_q_executor):
    airlock.enqueue(any_function, ...)  # All go via async_task()
```

**Huey executor** checks for `.schedule()`:

```python
with airlock.scope(executor=huey_executor):
    airlock.enqueue(huey_task, ...)      # Dispatches via .schedule()
    airlock.enqueue(plain_function, ...) # Falls back to sync
```

**Dramatiq executor** checks for `.send()`:

```python
with airlock.scope(executor=dramatiq_executor):
    airlock.enqueue(dramatiq_actor, ...)  # Dispatches via .send()
    airlock.enqueue(plain_function, ...)  # Falls back to sync
```

**Dependencies**: Each executor requires its corresponding task queue library to be installed. Import the executor only if you have the library available (e.g., `celery_executor` requires `celery`, `django_q_executor` requires `django-q`).

Executors are **composable** — use different executors with different scopes, or write your own for custom dispatch mechanisms.

## Django integration

### Setup

```python
# settings.py
MIDDLEWARE = [
    # ...
    "airlock.integrations.django.AirlockMiddleware",
]
```

The middleware wraps each request in a scope. Flushes on 1xx/2xx/3xx, discards on 4xx/5xx. Dispatch is deferred to `transaction.on_commit()` automatically.

### Settings

All optional. Configure via the `AIRLOCK` dict:

```python
# settings.py
AIRLOCK = {
    # Default policy - dotted path or callable
    "DEFAULT_POLICY": "airlock.AllowAll",

    # Defer to transaction.on_commit()
    "USE_ON_COMMIT": True,

    # Database alias for on_commit
    "DATABASE_ALIAS": "default",

    # Task executor: dotted path to executor callable, or None for sync
    "TASK_BACKEND": None,
}
```

**TASK_BACKEND** is a dotted import path to an executor callable:

| Setting | Behavior |
|---------|----------|
| `None` (default) | Tasks run synchronously at flush |
| `"airlock.integrations.executors.celery.celery_executor"` | Dispatch via Celery `.delay()` / `.apply_async()` |
| `"airlock.integrations.executors.django_q.django_q_executor"` | Dispatch via django-q `async_task()` |
| `"airlock.integrations.executors.huey.huey_executor"` | Dispatch via Huey `.schedule()` |
| `"airlock.integrations.executors.dramatiq.dramatiq_executor"` | Dispatch via Dramatiq `.send()` |
| `"myapp.executors.custom_executor"` | Your custom executor |

You can always pass an executor explicitly to override the setting:

```python
from airlock.integrations.executors.django_q import django_q_executor

# Explicit executor (ignores TASK_BACKEND setting)
with airlock.scope(_cls=DjangoScope, executor=django_q_executor):
    ...
```

### Custom flush behavior

If you don't want task execution to depend on HTTP response code, you can subclass the middleware:

```python
# myapp/middleware.py
from airlock.integrations.django import AirlockMiddleware

class MyAirlockMiddleware(AirlockMiddleware):
    def should_flush(self, request, response) -> bool:
        # Only flush on 2xx
        return 200 <= response.status_code < 300
```

### Management commands

```python
from django.core.management.base import BaseCommand
from airlock.integrations.django import airlock_command

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    @airlock_command
    def handle(self, *args, **options):
        # If --dry-run, all enqueued effects are dropped
        do_migration_stuff()
```

### DjangoScope

Use directly if you need transaction-aware scoping outside middleware:

```python
from airlock.integrations.django import DjangoScope

with airlock.scope(_cls=DjangoScope):
    # dispatch deferred to transaction.on_commit()
    ...
```

### Using django-q

django-q tasks work with airlock via the `django_q_executor`:

```python
# settings.py
AIRLOCK = {
    "TASK_BACKEND": "airlock.integrations.executors.django_q.django_q_executor",
}
```

Now all tasks enqueued in `DjangoScope` will dispatch via `async_task()`:

```python
from airlock.integrations.django import DjangoScope

def process_order(order_id):
    # Plain function - no @task decorator needed
    ...

with transaction.atomic():
    with airlock.scope(_cls=DjangoScope):
        order.save()
        airlock.enqueue(process_order, order.id)
# Dispatches via django_q.tasks.async_task() after commit ✓
```

**How it works:**

1. **Lifecycle** — `DjangoScope` defers flush to `transaction.on_commit()`
2. **Execution** — `django_q_executor` dispatches via `async_task()`
3. **Separation** — Scope and executor are independent concerns

You can use `django_q_executor` with **any** scope type, not just `DjangoScope`:

```python
from airlock.integrations.executors.django_q import django_q_executor

# Use django-q without Django transaction semantics
with airlock.scope(executor=django_q_executor):
    airlock.enqueue(my_task, ...)
# Dispatches immediately at flush (no on_commit defer)
```

**Dispatch options:**

`_dispatch_options` are passed directly to `async_task()`:

```python
airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={
        "group": "high-priority",
        "hook": "my_hook",
        "timeout": 60,
    }
)
# Calls: async_task(send_email, user_id=123, group="high-priority", hook="my_hook", timeout=60)
```

## Celery integration

Wrap task execution in a scope for predictable execution boundaries and policy control:

```python
from airlock.integrations.celery import AirlockTask

@app.task(base=AirlockTask)
def process_order(order_id):
    # Any enqueue() calls here are buffered
    airlock.enqueue(send_receipt, order_id)
    airlock.enqueue(notify_warehouse, order_id)
# Flushes on success, discards on exception
```

## Migrating existing codebases

If you have a large codebase with `my_task.delay()` sprinkled throughout, migrating to airlock can be a pain. Helpers are provided to assist with this process.

### Selectively migrating tasks

You can selectively apply base class `LegacyTaskShim` to your task definitions to intercept `.delay()` calls and route through airlock without changing your calling code:

```python
from airlock.integrations.celery import LegacyTaskShim

@app.task(base=LegacyTaskShim)
def old_task(arg):
    ...

# This now emits DeprecationWarning and routes through airlock, respecting execution boundaries and policy control:
old_task.delay(123)
```

**Note:** `LegacyTaskShim` is strict — it requires an active scope. Calling `.delay()` outside a scope raises `NoScopeError`. This differs from `install_global_intercept()`, which warns but allows passthrough when no scope exists. Use `LegacyTaskShim` for tasks you've fully migrated; use global intercept for gradual migration where some code paths may not have scopes yet.

**Important:** Intercepted `.delay()` and `.apply_async()` calls return `None`, not an `AsyncResult`. This is intentional — when dispatch is deferred to scope flush, there is no result to return at call time. If your code relies on the return value (e.g., `result = task.delay(...); result.get()`), you'll need to refactor. This is a feature, not a bug: it forces you to decouple "intent" from "result tracking".

### Blanket-migrating tasks

For large codebases where applying `LegacyTaskShim` to every task is impractical, you can install a global intercept that patches all Celery tasks at once:

```python
# celery.py or settings.py (at app startup)
from celery import Celery
from airlock.integrations.celery import install_global_intercept

app = Celery(...)

# Patch Task.delay(), Task.apply_async(), and Task.__call__() globally
install_global_intercept(app)
```

> ⚠️ **Global intercept is a migration tool, not a steady-state architecture.**
>
> - It monkey-patches Celery globally
> - It changes return values of `.delay()` inside scopes (returns `None`)
> - It implicitly introduces execution scopes into all tasks
>
> Use this to migrate legacy codebases. New code should prefer `airlock.enqueue()`, explicit `AirlockTask` base classes, and explicit scopes.

This does two things:

1. **Intercepts `.delay()` and `.apply_async()` calls**: All calls emit a `DeprecationWarning` encouraging migration to `airlock.enqueue()`. Inside a scope, calls are routed through airlock; outside a scope, they pass through to Celery.

2. **Wraps task execution in scopes**: Every task automatically runs inside an airlock scope (like using `AirlockTask`). This means any `.delay()` calls made *during* task execution are buffered and flush when the task completes.

| Context | Behavior |
|---------|----------|
| **Inside `airlock.scope()`** | Routed through airlock, returns `None` |
| **Outside any scope** | Passes through to Celery, returns `AsyncResult` |
| **Both** | Emits `DeprecationWarning` |

```python
# Outside any scope - warns but works
send_email.delay(user_id=123)  # DeprecationWarning, immediate dispatch

# Inside a scope - intercepted
with airlock.scope():
    send_email.delay(user_id=123)  # DeprecationWarning, buffered, returns None
# Dispatches here when scope exits

# Inside a task (with wrap_task_execution=True)
@app.task
def process_order(order_id):
    send_receipt.delay(order_id)  # Buffered in task's scope
# Flushes when task completes successfully
```

To disable task execution wrapping (intercept only):

```python
install_global_intercept(app, wrap_task_execution=False)
```

**Important:** Call `install_global_intercept()` only once, at app startup, after Celery is configured but before tasks are invoked. Calling it multiple times raises `RuntimeError`.

**Note:** If using `wrap_task_execution=True` (default), do not also use `AirlockTask` as a base class — this creates redundant nested scopes. Choose one approach: either global intercept with wrapping, or explicit `AirlockTask` inheritance.

## Invariants

1. **Policies cannot enqueue.** Calling `enqueue()` from a policy raises `PolicyEnqueueError`.

2. **Side effects escape in one place.** Only scope flush dispatches. No `.delay()` in domain code.

3. **No scope = error.** Calling `enqueue()` outside a scope raises `NoScopeError`. This is intentional: airlock requires explicit lifecycle boundaries. Side effects should not escape silently. If you want auto-dispatch without a scope, you don't need airlock — just call `.delay()` directly. The strictness is a feature, not a limitation.

4. **Dispatch order is FIFO.** On `flush()`, intents are dispatched in the order they were enqueued, after policy filtering. The `allows()` API is per-intent, enforcing FIFO by construction — policies cannot reorder. Policies are boolean gates (allow/drop), not schedulers. If you need reordering, batching, or fan-out, that belongs in dispatch logic (override `Scope._dispatch_all`), not in policy logic.

5. **Flush is not atomic.** If dispatch fails mid-flush, earlier intents may have already dispatched. Airlock does not isolate dispatch failures — if dispatching an intent raises, flush aborts immediately. This is intentional: dispatch failures indicate infrastructure or configuration errors and must surface loudly. Airlock prefers visible failure over silent partial success.

## Crash semantics

Airlock buffers intents in memory. If the process terminates before flush, **intents are lost**.

This is intentional and explicit:

- OOM, SIGKILL, or crash mid-scope = intents gone
- No hidden persistence, no implicit durability
- The scope boundary is the contract

If you need recoverability:

- Use a transactional outbox pattern alongside airlock
- Log intents eagerly for audit purposes
- Accept that "intent expressed but not dispatched" is a valid failure mode

Airlock makes the boundary explicit. What you do at that boundary is up to you.

## Advanced: Writing custom policies

Policies implement two hooks: `on_enqueue` and `allows`. Understanding their contract unlocks powerful patterns.

### The policy protocol

```python
class Policy(Protocol):
    def on_enqueue(self, intent: Intent) -> None:
        """Called when an intent is added to the buffer. Observe or raise."""
        ...

    def allows(self, intent: Intent) -> bool:
        """Called at flush time. Return True to dispatch, False to drop."""
        ...
```

This design enforces FIFO by construction. Policies are per-intent boolean gates — they can filter but cannot reorder. If you need batching, reordering, or fan-out, override `Scope._dispatch_all()`.

### `on_enqueue`: observe or reject

Called immediately when `enqueue()` is invoked. The return value is ignored.

**What you can do:**
- **Observe** — log, increment counters, record metrics
- **Reject** — raise an exception to prevent buffering

**What you cannot do:**
- Transform the intent (it's frozen, return is ignored)
- Call `enqueue()` (raises `PolicyEnqueueError`)

**When to raise vs. deny later:**

| Raise in `on_enqueue` | Return False in `allows` |
|-----------------------|----------------------|
| Fail-fast feedback | Silent filtering |
| Stack trace points to call site | Deferred, no trace |
| "This is a bug" | "Drop these, it's fine" |

`AssertNoEffects` raises in `on_enqueue` because tests should fail immediately at the offending line. `DropAll` returns `False` in `allows` because silent suppression is the goal.

### `allows`: per-intent gate

Called at flush time for each intent. Return `True` to dispatch, `False` to drop.

**What you can do:**
- **Filter** — return `False` to drop an intent
- **Log/observe** — perform side effects (logging, metrics) while allowing

**What you cannot do (by design):**
- Transform intents
- Reorder intents
- Batch/coalesce intents
- Duplicate intents

This is intentional. The `allows()` API enforces FIFO ordering by construction. For advanced dispatch patterns (batching, priority ordering, fan-out), override `Scope._dispatch_all()`.

**Example: Logging policy**

```python
class LoggingPolicy:
    def __init__(self, logger):
        self.logger = logger

    def on_enqueue(self, intent):
        self.logger.info(f"Enqueueing: {intent.name}")

    def allows(self, intent):
        self.logger.info(f"Dispatching: {intent.name}")
        return True
```

**Example: Rate-limited policy**

```python
class RateLimitPolicy:
    def __init__(self, max_per_flush: int):
        self.max = max_per_flush
        self._count = 0

    def on_enqueue(self, intent):
        pass

    def allows(self, intent):
        if self._count >= self.max:
            return False
        self._count += 1
        return True
```

### Local policies and the flush pipeline

When you use `airlock.policy()`, the policy is captured on each intent at enqueue time. At flush, local policies are checked per-intent (innermost first):

```
for each intent:
    for policy in reversed(local_policies):
        if not policy.allows(intent): drop
    if not scope_policy.allows(intent): drop
    dispatch(intent)
```

If any policy returns `False`, the intent is dropped. All policies use the same `allows()` interface.

| | Scope policy | Local policy |
|---|---|---|
| Set when | Scope creation | `airlock.policy()` context |
| `on_enqueue` | Called once per intent | Called once per intent |
| `allows` | Called per-intent at flush | Called per-intent at flush |

### Cross-phase state

Policies should not rely on cross-intent coordination. While policies may maintain internal state, decisions are evaluated per-intent and must not affect ordering or dispatch structure. If you need to "tag" an intent at enqueue time for later processing:

1. **Inspect intent properties in `allows`** — usually sufficient
2. **Use policy internal state** — key by `id(intent)` if truly needed
3. **Put context in the intent** — use `_origin` or `_dispatch_options` at enqueue time

This is intentionally simple. Most policies don't need cross-phase memory.

---

# Architecture

Airlock has three orthogonal extension points. Understanding their separation makes advanced usage intuitive.

## The Three Extension Points

| Extension Point | Purpose | When to Customize |
|----------------|---------|-------------------|
| **Policy** | Observe/filter intents | Logging, blocking specific tasks, test assertions |
| **Executor** | How intents execute | Different task queues (Celery, django-q), threading, remote execution |
| **Scope** | When/whether to flush | Transaction boundaries, durable buffering (outbox pattern) |

These concerns are **independent** and can be mixed freely.

### Policy = Observe and Filter

Policies implement two hooks:
- `on_enqueue(intent)` — Called when intent is buffered. Observe or raise.
- `allows(intent)` — Called at flush. Return `True` to dispatch, `False` to drop.

Policies are **stateless boolean gates**. They judge intents but don't affect ordering or execution mechanism.

**Example: Block specific tasks**
```python
policy = airlock.BlockTasks({"send_sms", "expensive_rebuild"})
with airlock.scope(policy=policy):
    airlock.enqueue(send_email)  # Dispatches
    airlock.enqueue(send_sms)    # Dropped
```

### Executor = How to Execute

Executors are callables that take an `Intent` and execute it via some dispatch mechanism.

**Built-in executors** (in `airlock.integrations.executors`):
- `sync_executor` — Synchronous execution (default)
- `celery_executor` — Dispatch via `.delay()` / `.apply_async()`
- `django_q_executor` — Dispatch via `async_task()`
- `huey_executor` — Dispatch via `.schedule()`
- `dramatiq_executor` — Dispatch via `.send()`

**Example: Use django-q for all tasks**
```python
from airlock.integrations.executors.django_q import django_q_executor

with airlock.scope(executor=django_q_executor):
    airlock.enqueue(process_order, order_id=123)
# Dispatched via django_q.tasks.async_task()
```

Executors are **pluggable** — you can write your own for threadpools, AWS Lambda, remote sandboxes, etc.

### Scope = When and Whether to Flush

Scopes control:
- **Buffer storage** (in-memory list, database table, etc.)
- **Flush timing** (end of scope, after transaction commit, etc.)
- **Flush decision** (always, on success, conditional, etc.)

**Built-in scope types**:
- `Scope` — Flushes on normal exit, discards on exception
- `DjangoScope` — Defers flush to `transaction.on_commit()`
- Custom scopes for outbox pattern, batching, etc.

**Example: Transaction-aware scope**
```python
from airlock.integrations.django import DjangoScope

with transaction.atomic():
    with airlock.scope(_cls=DjangoScope):
        order.save()
        airlock.enqueue(send_receipt, order.id)
# Flush deferred until transaction commits ✓
```

## Composing Extension Points

**Scope type**, **executor**, and **policy** are orthogonal:

```python
# Django transaction boundary + django-q executor + logging policy
from airlock.integrations.django import DjangoScope
from airlock.integrations.executors.django_q import django_q_executor

with airlock.scope(
    _cls=DjangoScope,              # When: defer to on_commit
    executor=django_q_executor,    # How: via async_task()
    policy=airlock.LogOnFlush()    # What: log everything
):
    do_stuff()
```

You can mix:
- `DjangoScope` + `celery_executor` ✓
- Base `Scope` + `django_q_executor` ✓
- Custom scope + custom executor ✓

## When to Use Each Extension Point

**Use Policy when:**
- Filtering which tasks dispatch (block, allow, assert)
- Observing intents for logging/metrics
- Testing that code doesn't enqueue

**Use Executor when:**
- Changing how tasks run (queue, threading, remote)
- All executors are pluggable integrations

**Use Scope subclass when:**
- Changing when effects escape (transaction boundaries)
- Changing buffer persistence (outbox pattern)
- Custom flush logic (batching, conditional dispatch)

**Example: Outbox Pattern (Scope + Executor)**

The transactional outbox pattern needs both a custom scope (for durable buffering) and an executor (for marking as ready):

```python
class OutboxScope(Scope):
    """Durable scope that persists intents to database."""

    def _add(self, intent):
        super()._add(intent)
        # Persist immediately (in transaction)
        TaskOutbox.objects.create(
            task_name=intent.name,
            args=intent.args,
            kwargs=intent.kwargs,
            status='pending'
        )

    def _dispatch_all(self, intents):
        # Mark as ready instead of executing
        # Separate worker will dispatch later
        for intent in intents:
            TaskOutbox.objects.filter(...).update(status='ready')
```

From airlock's perspective this is a **scope** concern (persistence + lifecycle) -- a separate external process would then be responsible for polling the outbox and actually dispatching tasks.

---

# API Reference

## Three layers of API

Airlock provides three layers of API for different use cases:

| Layer | Audience | Use when |
|-------|----------|----------|
| **Context manager** | Application code | Default — automatic lifecycle, just works |
| **Subclassing** | Customization | Need custom flush/discard logic |
| **Imperative** | Integration authors | Building middleware, task wrappers, frameworks |

Most code should use the context manager. Drop down a layer only when you need its capabilities.

---

## Layer 1: Context Manager (Application Code)

The context manager is the primary API. It handles lifecycle automatically.

### `airlock.scope(policy=None, *, _cls=Scope)`

Create a lifecycle boundary for side effects.

```python
with airlock.scope() as s:
    airlock.enqueue(task_a)
    airlock.enqueue(task_b)
# Intents dispatch here (on normal exit)
# Intents are discarded if an exception is raised
```

**Parameters:**
- `policy` — Policy controlling what intents are allowed. Defaults to `AllowAll()`.
- `_cls` — Scope class to use. For subclassing (see Layer 2).

**Behavior:**
- On normal exit: calls `flush()` — intents are dispatched (subject to policy)
- On exception: calls `discard()` — intents are dropped

**Nested scopes** create independent buffers:

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)  # Goes to outer

    with airlock.scope() as inner:
        airlock.enqueue(task_b)  # Goes to inner
    # inner flushes here

    airlock.enqueue(task_c)  # Goes to outer
# outer flushes here
```

### `airlock.enqueue(task, *args, _origin=None, _dispatch_options=None, **kwargs)`

Express intent to perform a side effect.

```python
airlock.enqueue(send_email, user_id=123)
airlock.enqueue(sync_warehouse, item_id=456, _dispatch_options={"queue": "low"})
```

**Parameters:**
- `task` — The callable to execute (Celery task, function, etc.)
- `*args` — Positional arguments for the task
- `_origin` — Optional origin metadata for debugging/observability
- `_dispatch_options` — Optional dispatch options (countdown, queue, etc.)
- `**kwargs` — Keyword arguments for the task

**Raises:**
- `NoScopeError` — If no scope is active
- `PolicyEnqueueError` — If called from within a policy callback

### `airlock.policy(p)`

Context manager for local policy control without creating a new buffer.

```python
with airlock.scope():
    airlock.enqueue(task_a)  # Will dispatch

    with airlock.policy(DropAll()):
        airlock.enqueue(task_b)  # Won't dispatch

    airlock.enqueue(task_c)  # Will dispatch
```

All intents go to the same buffer. The policy is captured on each intent at enqueue time.

### `airlock.get_current_scope()`

Get the currently active scope, or `None` if no scope is active.

```python
scope = airlock.get_current_scope()
if scope:
    print(f"Buffered intents: {len(scope.intents)}")
```

---

## Layer 2: Subclassing (Customization)

Subclass `Scope` to customize flush/discard behavior. This is the recommended approach for:
- Flush on error (e.g., error notification patterns)
- Conditional flush based on scope state
- Custom dispatch logic (e.g., `transaction.on_commit()`)

### `Scope.should_flush(error)`

Override this method to control whether the scope flushes or discards on exit.

```python
class Scope:
    def should_flush(self, error: BaseException | None) -> bool:
        """
        Decide terminal action when context manager exits.

        Args:
            error: The exception that caused exit, or None for normal exit.

        Returns:
            True to flush (dispatch intents), False to discard.

        Default behavior: flush on success, discard on error.
        """
        return error is None
```

**Example: Always flush (even on error)**

```python
class AlwaysFlushScope(Scope):
    """Flush even on error — for error notification patterns."""

    def should_flush(self, error: BaseException | None) -> bool:
        return True

# Usage
with airlock.scope(_cls=AlwaysFlushScope):
    airlock.enqueue(send_alert, context="starting")
    do_risky_stuff()  # Even if this raises, send_alert dispatches
```

**Example: Conditional flush based on intents**

```python
class FlushIfWorthItScope(Scope):
    """Only flush if at least one intent would pass local policies."""

    def should_flush(self, error: BaseException | None) -> bool:
        if error:
            return False
        # Don't bother flushing if nothing would pass local policies
        return any(intent.passes_local_policies() for intent in self.intents)
```

**Example: Flush based on intent priority**

```python
class FlushOnlyCriticalScope(Scope):
    """Only flush if there's a critical intent."""

    def should_flush(self, error: BaseException | None) -> bool:
        if error:
            return False
        return any(
            intent.dispatch_options and
            intent.dispatch_options.get("priority") == "critical"
            for intent in self.intents
        )
```

### `Scope._dispatch_all(intents)`

Override to customize how intents are dispatched (e.g., defer to `on_commit`).

```python
class DeferredScope(Scope):
    """Defer dispatch to transaction.on_commit()."""

    def _dispatch_all(self, intents: list[Intent]) -> None:
        from django.db import transaction

        def do_dispatch():
            for intent in intents:
                _execute(intent)

        transaction.on_commit(do_dispatch)
```

### Available state in subclasses

Subclasses have access to:

| Property | Type | Description |
|----------|------|-------------|
| `self.intents` | `list[Intent]` | Read-only list of buffered intents |
| `self._policy` | `Policy` | The scope's policy |
| `self.is_flushed` | `bool` | True after `flush()` called |
| `self.is_discarded` | `bool` | True after `discard()` called |

---

## Layer 3: Imperative API (Integration Authors)

The imperative API exposes explicit lifecycle control for building framework integrations (middleware, task wrappers, etc.).

**When to use this:**
- Django middleware that flushes based on response status
- Celery task wrappers
- Custom request/response frameworks
- Any context where you need to interleave framework logic between deactivation and terminal state

### `Scope.enter()`

Activate this scope. Sets the context var so `enqueue()` routes to this scope.

```python
s = Scope(policy=AllowAll())
s.enter()  # Scope is now active
# ... enqueue() calls go to this scope ...
```

**Returns:** `self` (for chaining)

**Raises:** `ScopeStateError` if scope is already active

### `Scope.exit()`

Deactivate this scope. Resets the context var to the previous scope (or None).

```python
s.exit()  # Scope is no longer active
# ... must still call flush() or discard() ...
```

**Raises:** `ScopeStateError` if scope is not active

### `Scope.flush()`

Apply policy and dispatch all buffered intents.

```python
dispatched = s.flush()  # Returns list of intents that were dispatched
```

**Returns:** List of intents that were dispatched (after policy filtering)

**Raises:**
- `ScopeStateError` if already flushed/discarded
- `ScopeStateError` if scope is still active (must call `exit()` first)

### `Scope.discard()`

Drop all buffered intents without dispatching.

```python
discarded = s.discard()  # Returns list of intents that were discarded
```

**Returns:** List of intents that were discarded

**Raises:**
- `ScopeStateError` if already flushed/discarded
- `ScopeStateError` if scope is still active (must call `exit()` first)

### Integration pattern

The typical pattern for integrations:

```python
def middleware(get_response, request):
    s = Scope(policy=get_policy())
    s.enter()

    error: BaseException | None = None
    try:
        response = get_response(request)
    except BaseException as e:
        error = e
        raise
    finally:
        s.exit()  # Deactivate first

    # Now decide terminal action (scope is inactive)
    if error:
        s.discard()
    elif response.status_code < 400:
        s.flush()
    else:
        s.discard()

    return response
```

**Key invariants:**
- Must call `exit()` before `flush()` or `discard()`
- Can only flush or discard once (terminal operations)
- Cannot add intents after flush or discard

### Comparison: Context manager vs Imperative

The context manager is equivalent to:

```python
# This:
with airlock.scope(policy=policy) as s:
    do_stuff()

# Is equivalent to:
s = Scope(policy=policy)
s.enter()
error = None
try:
    do_stuff()
except BaseException as e:
    error = e
    raise
finally:
    s.exit()
    if not s.is_flushed and not s.is_discarded:
        if s.should_flush(error):
            s.flush()
        else:
            s.discard()
```

The imperative API gives you control over each step. Use it when you need to insert logic between steps.

---

## Policies

### Built-in policies

| Policy | `on_enqueue` | `allows` | Use case |
|--------|--------------|----------|----------|
| `AllowAll` | No-op | `True` | Default — allow everything |
| `DropAll` | No-op | `False` | Suppress all side effects |
| `AssertNoEffects` | Raises `PolicyViolation` | `False` | Tests — fail on any enqueue |
| `BlockTasks(names)` | Optionally raises | `name not in names` | Block specific tasks |
| `LogOnFlush(logger)` | No-op | Logs, returns `True` | Debugging/audit |
| `CompositePolicy(*ps)` | Calls all | `all(p.allows())` | Combine policies |

### `BlockTasks`

```python
# Block silently
policy = BlockTasks({"myapp.tasks:send_email", "myapp.tasks:send_sms"})

# Block and raise immediately on enqueue
policy = BlockTasks({"dangerous_task"}, raise_on_enqueue=True)
```

---

## Intent

Represents a buffered side effect.

| Property | Type | Description |
|----------|------|-------------|
| `task` | `Callable` | The callable to execute |
| `args` | `tuple` | Positional arguments |
| `kwargs` | `dict` | Keyword arguments |
| `name` | `str` | Derived name for logging |
| `origin` | `str \| None` | Optional origin metadata |
| `dispatch_options` | `dict \| None` | Queue options (countdown, queue, etc.) |
| `local_policies` | `tuple[Policy, ...]` | Captured policy stack |

### `Intent.passes_local_policies()`

Check if this intent passes its captured local policies.

```python
if intent.passes_local_policies():
    print(f"{intent.name} passes local policies")
```

**Note:** This only checks local policies. It does not consider:
- Scope-level policy
- Whether the scope flushes or discards
- Dispatch execution success

---

## Errors

All errors inherit from `AirlockError`.

| Error | When raised |
|-------|-------------|
| `NoScopeError` | `enqueue()` called outside a scope |
| `PolicyEnqueueError` | `enqueue()` called from within a policy |
| `ScopeStateError` | Invalid operation for scope's lifecycle state |
| `PolicyViolation` | Policy explicitly rejected an intent |

---

## That's it

Does one thing! Hopefully well.
