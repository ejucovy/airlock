# The Problem

Why does airlock exist? What problem does it solve?

## The Dangerous Pattern

Side effects deep in the call stack are common but problematic:

```python
class Order(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.status == "shipped":
            notify_warehouse.delay(self.id)
            send_confirmation_email.delay(self.id)
```

This looks reasonable. The model knows when to trigger notifications. DRY principle. Encapsulated.

**But it's a trap.**

## What Goes Wrong

### 1. No Opt-Out

```python
# Migration script
for order in Order.objects.all():
    order.status = "processed"
    order.save()  # 🔥 Fires 10,000 warehouse notifications
```

Every save triggers the side effect. Migrations, fixtures, bulk operations, tests - everything.

### 2. Invisible at Call Site

```python
order.status = "shipped"
order.save()  # Looks innocent
```

You can't tell from reading this that it fires tasks. You have to know to check inside `save()`.

### 3. Testing is Painful

Options:
- Mock at task level → Fragile, couples tests to implementation
- Run real broker → Slow
- `CELERY_ALWAYS_EAGER=True` → Hides async bugs

None are good.

### 4. Bulk Operations Explode

```python
# Want to update 10,000 orders
Order.objects.filter(old_status="pending").update(status="processed")
# ✓ One query

# But you have side effects in save()
for order in Order.objects.filter(old_status="pending"):
    order.status = "processed"
    order.save()  # 🔥 10,000 task dispatches
```

### 5. Re-entrancy Hell

```python
class User(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        enrich_from_api.delay(self.id)

@celery.task
def enrich_from_api(user_id):
    user = User.objects.get(id=user_id)
    data = call_external_api(user.email)
    user.age = data['age']
    user.income = data['income']
    user.save()  # 🔥 Triggers enrich_from_api again!
```

Now you're adding flags:

```python
def save(self, *args, _skip_enrich=False, **kwargs):
    super().save(*args, **kwargs)
    if not _skip_enrich:
        enrich_from_api.delay(self.id)
```

And threading them everywhere. Yikes.

## The Root Cause

The problem isn't **where** the intent is expressed.

The problem is:
1. **Effects are silent** - invisible at call site
2. **Effects escape immediately** - no control

## The Standard Solution

Move side effects to the edge:

```python
# Model stays pure
class Order(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

# View handles side effects
def ship_order(request, order_id):
    order = Order.objects.get(id=order_id)
    order.status = "shipped"
    order.save()

    # Explicit side effects
    notify_warehouse.delay(order.id)
    send_confirmation_email.delay(order.id)

    return HttpResponse("OK")
```

This works! It's explicit, controllable, testable.

**But you lose:**
- Encapsulation - every caller must remember to fire tasks
- DRY - duplicate side effect logic across call sites
- Domain knowledge - the Order doesn't express its own behavior

## The Airlock Solution

Express intent in the model, but effects don't escape immediately:

```python
import airlock

class Order(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.status == "shipped":
            airlock.enqueue(notify_warehouse, self.id)        # Buffered
            airlock.enqueue(send_confirmation_email, self.id) # Buffered
```

The **execution context** controls what happens:

```python
# Production: effects escape
with airlock.scope():
    order.status = "shipped"
    order.save()
# Effects dispatch here

# Migration: suppress everything
with airlock.scope(policy=airlock.DropAll()):
    order.status = "shipped"
    order.save()
# Nothing dispatches

# Test: assert no effects
with airlock.scope(policy=airlock.AssertNoEffects()):
    order.status = "pending"  # Still testable
    order.save()              # Raises if side effects attempted
```

**You get:**
- ✅ Encapsulation - intent in the domain object
- ✅ DRY - define once
- ✅ Control - execution context decides
- ✅ Visibility - inspect before dispatch
- ✅ Testing - suppress or assert

## Key Insight

Airlock separates **expressing intent** from **executing effects**.

Intent can live close to domain logic.
Execution happens at boundaries you control.

## Next

- [Core model](core-model.md) - The 3 concerns (Policy/Executor/Scope)
- [How it composes](how-it-composes.md) - Nested scopes and provenance
