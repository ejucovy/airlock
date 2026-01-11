# Core API

The main airlock module. Import with `import airlock`.

## Functions

::: airlock.scope
    options:
      show_root_heading: true

::: airlock.enqueue
    options:
      show_root_heading: true

::: airlock.policy
    options:
      show_root_heading: true

::: airlock.get_current_scope
    options:
      show_root_heading: true

## Classes

::: airlock.Scope
    options:
      show_root_heading: true
      members:
        - intents
        - own_intents
        - captured_intents
        - is_flushed
        - is_discarded
        - is_active
        - enter
        - exit
        - flush
        - discard
        - should_flush
        - before_descendant_flushes

::: airlock.Intent
    options:
      show_root_heading: true
      members:
        - task
        - args
        - kwargs
        - origin
        - dispatch_options
        - name
        - local_policies
        - passes_local_policies

## Protocols

::: airlock.Policy
    options:
      show_root_heading: true

::: airlock.Executor
    options:
      show_root_heading: true

## Built-in Policies

::: airlock.AllowAll
    options:
      show_root_heading: true

::: airlock.DropAll
    options:
      show_root_heading: true

::: airlock.AssertNoEffects
    options:
      show_root_heading: true

::: airlock.BlockTasks
    options:
      show_root_heading: true

::: airlock.LogOnFlush
    options:
      show_root_heading: true

::: airlock.CompositePolicy
    options:
      show_root_heading: true

## Exceptions

::: airlock.AirlockError
    options:
      show_root_heading: true

::: airlock.UsageError
    options:
      show_root_heading: true

::: airlock.NoScopeError
    options:
      show_root_heading: true

::: airlock.PolicyEnqueueError
    options:
      show_root_heading: true

::: airlock.ScopeStateError
    options:
      show_root_heading: true

::: airlock.PolicyViolation
    options:
      show_root_heading: true
