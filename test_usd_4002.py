"""OpenUSD PR #4002 regression tests, runnable against any installed USD.

These are the upstream unit tests added by
https://github.com/PixarAnimationStudios/OpenUSD/pull/4002
("[usdPhysics] fix for a multithreaded crash if one rigidbody has multiple
colliders beneath"), lightly adapted to run standalone (plain unittest, no USD
test harness).

On a vulnerable USD (< 26.05) the multithreaded LoadUsdPhysicsFromRange races
inside _FinalizeCollisionDescs<...> and corrupts the heap (SIGSEGV /
malloc_consolidate / double free / unaligned tcache chunk) -- the process dies
before any assertion runs. On a fixed USD (>= 26.05) both tests pass.

Run:
    python -m unittest test_usd_4002 -v
or:
    python test_usd_4002.py
"""
import unittest
from pxr import Usd, UsdGeom, UsdPhysics, Sdf


class TestMultithreadedPhysicsParse(unittest.TestCase):
    def test_rigidbody_collision_multithreading_parse(self):
        """Single rigid body with many collision objects: multithreaded parse
        must work correctly (and not crash)."""
        NUM_COLLIDERS = 1000

        stage = Usd.Stage.CreateInMemory()
        body = UsdGeom.Xform.Define(stage, "/Body")
        UsdPhysics.RigidBodyAPI.Apply(body.GetPrim())

        for k in range(NUM_COLLIDERS):
            sphere = UsdGeom.Sphere.Define(stage, f"/Body/SphereCollider_{k}")
            UsdPhysics.CollisionAPI.Apply(sphere.GetPrim())

        ret_dict = UsdPhysics.LoadUsdPhysicsFromRange(
            stage, [Sdf.Path.absoluteRootPath])

        collider_count = 0
        for key, value in ret_dict.items():
            prim_paths, descs = value
            if key == UsdPhysics.ObjectType.SphereShape:
                collider_count = len(prim_paths)

        self.assertEqual(
            collider_count, NUM_COLLIDERS,
            f"Expected {NUM_COLLIDERS} colliders, got {collider_count}")

    def test_custom_geometry_multithreading_parse(self):
        """Many custom-shape colliders parsed in parallel must produce the
        correct customGeometryToken for every descriptor."""
        NUM_CUSTOM_COLLIDERS = 500

        stage = Usd.Stage.CreateInMemory()
        UsdPhysics.Scene.Define(stage, "/physicsScene")

        body = UsdGeom.Xform.Define(stage, "/Body")
        UsdPhysics.RigidBodyAPI.Apply(body.GetPrim())

        layer = stage.GetEditTarget().GetLayer()

        token_a = "CustomGeomA_API"
        token_b = "CustomGeomB_API"

        expected = []
        for k in range(NUM_CUSTOM_COLLIDERS):
            prim_path = f"/Body/CustomCollider_{k}"
            UsdGeom.Cube.Define(stage, prim_path)

            token = token_a if k % 2 == 0 else token_b
            expected.append((prim_path, token))

            primSpec = Sdf.CreatePrimInLayer(layer, prim_path)
            listOp = Sdf.TokenListOp()
            listOp.prependedItems = [token, "PhysicsCollisionAPI"]
            primSpec.SetInfo(Usd.Tokens.apiSchemas, listOp)

        custom_tokens = UsdPhysics.CustomUsdPhysicsTokens()
        custom_tokens.shapeTokens.append(token_a)
        custom_tokens.shapeTokens.append(token_b)

        ret_dict = UsdPhysics.LoadUsdPhysicsFromRange(
            stage, [Sdf.Path.absoluteRootPath], [], custom_tokens)

        self.assertIn(UsdPhysics.ObjectType.CustomShape, ret_dict)
        prim_paths, descs = ret_dict[UsdPhysics.ObjectType.CustomShape]

        self.assertEqual(len(descs), NUM_CUSTOM_COLLIDERS)

        expected_map = {p: t for p, t in expected}

        for prim_path, desc in zip(prim_paths, descs):
            path_str = str(prim_path)
            self.assertIn(
                path_str, expected_map, f"Unexpected prim path {path_str}")
            self.assertEqual(
                desc.customGeometryToken, expected_map[path_str],
                f"Wrong customGeometryToken for {path_str}: "
                f"got {desc.customGeometryToken}, "
                f"expected {expected_map[path_str]}")


if __name__ == "__main__":
    print("USD version:", Usd.GetVersion())
    unittest.main(verbosity=2)
