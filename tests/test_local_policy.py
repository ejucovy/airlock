"""Tests for local policy contexts."""

import airlock
from airlock import scope, policy, AllowAll, DropAll, BlockTasks


def task_a():
    pass


def task_b():
    pass


def task_c():
    pass


class TestLocalPolicyContext:
    """Tests for the policy() context manager."""

    def test_policy_captures_on_intent(self):
        """Test that intents capture active local policies."""
        with scope() as s:
            airlock.enqueue(task_a)

            with policy(DropAll()):
                airlock.enqueue(task_b)

            airlock.enqueue(task_c)

        # Check captured policies
        assert len(s.intents) == 3
        assert s.intents[0]._local_policies == ()
        assert len(s.intents[1]._local_policies) == 1
        assert isinstance(s.intents[1]._local_policies[0], DropAll)
        assert s.intents[2]._local_policies == ()

    def test_policy_filters_at_flush(self):
        """Test that local policies filter intents at flush time."""
        dispatched = []

        def track_a():
            dispatched.append("a")

        def track_b():
            dispatched.append("b")

        def track_c():
            dispatched.append("c")

        with scope():
            airlock.enqueue(track_a)

            with policy(DropAll()):
                airlock.enqueue(track_b)

            airlock.enqueue(track_c)

        assert dispatched == ["a", "c"]

    def test_nested_policy_contexts(self):
        """Test nested policy contexts stack."""
        with scope() as s:
            with policy(DropAll()):
                with policy(BlockTasks({"foo"})):
                    airlock.enqueue(task_a)

        # Both policies should be captured
        assert len(s.intents[0]._local_policies) == 2

    def test_nested_policy_all_apply(self):
        """Test that all nested policies are applied."""
        dispatched = []

        def track():
            dispatched.append(1)

        with scope():
            with policy(DropAll()):
                with policy(AllowAll()):
                    # Even though inner is AllowAll, outer DropAll still applies
                    airlock.enqueue(track)

        # DropAll should have blocked it
        assert dispatched == []

    def test_policy_does_not_affect_scope_buffer(self):
        """Test that all intents go to the same buffer regardless of policy."""
        with scope() as s:
            airlock.enqueue(task_a)

            with policy(DropAll()):
                airlock.enqueue(task_b)
                airlock.enqueue(task_c)

            airlock.enqueue(task_a)

        # All 4 intents should be in the buffer
        assert len(s.intents) == 4

    def test_intent_passes_local_policies(self):
        """Test the passes_local_policies() helper on Intent."""
        with scope() as s:
            airlock.enqueue(task_a)

            with policy(DropAll()):
                airlock.enqueue(task_b)

        assert s.intents[0].passes_local_policies() is True
        assert s.intents[1].passes_local_policies() is False

    def test_local_policies_property(self):
        """Test the local_policies property on Intent."""
        with scope() as s:
            with policy(DropAll()) as p:
                airlock.enqueue(task_a)

        policies = s.intents[0].local_policies
        assert len(policies) == 1
        assert isinstance(policies[0], DropAll)

    def test_block_tasks_local_policy(self):
        """Test BlockTasks as a local policy."""
        dispatched = []

        def allowed():
            dispatched.append("allowed")

        def blocked():
            dispatched.append("blocked")

        with scope() as s:
            with policy(BlockTasks({"blocked"})):
                airlock.enqueue(allowed)
                airlock.enqueue(blocked)

        assert dispatched == ["allowed"]

    def test_scope_policy_still_applies(self):
        """Test that scope policy applies after local policies."""
        dispatched = []

        def track():
            dispatched.append(1)

        # Even if no local policy, scope DropAll should block
        with scope(policy=DropAll()):
            airlock.enqueue(track)

        assert dispatched == []

    def test_scope_policy_and_local_policy_both_apply(self):
        """Test interaction between scope and local policies."""
        dispatched = []

        def task_allowed():
            dispatched.append("allowed")

        def task_blocked_local():
            dispatched.append("blocked_local")

        def task_blocked_scope():
            dispatched.append("blocked_scope")

        with scope(policy=BlockTasks({"task_blocked_scope"})):
            airlock.enqueue(task_allowed)

            with policy(BlockTasks({"task_blocked_local"})):
                airlock.enqueue(task_blocked_local)

            airlock.enqueue(task_blocked_scope)

        assert dispatched == ["allowed"]

    def test_innermost_policy_runs_first(self):
        """Test that innermost policy (closest to enqueue) runs first."""
        order = []

        class TrackingPolicy:
            def __init__(self, name):
                self.name = name

            def on_enqueue(self, intent):
                pass

            def allows(self, intent):
                order.append(self.name)
                return True

        with scope():
            with policy(TrackingPolicy("outer")):
                with policy(TrackingPolicy("middle")):
                    with policy(TrackingPolicy("inner")):
                        airlock.enqueue(task_a)

        assert order == ["inner", "middle", "outer"]
