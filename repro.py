"""Self-contained reproducer for the OpenUSD multithreaded UsdPhysics parse crash.

Builds an in-memory stage with one rigid body carrying many mesh colliders, then
calls UsdPhysics.LoadUsdPhysicsFromRange in a loop. On USD < 26.05 the default
(multithreaded) work pool races inside _FinalizeCollisionDescs<...> and corrupts
the heap (SIGSEGV / malloc_consolidate / double free / unaligned tcache chunk).

Env knobs: N (iterations, default 50), COLLIDERS (default 40),
PXR_WORK_THREAD_LIMIT=1 (serialize parse -> workaround).
"""
import os
from pxr import Usd, UsdGeom, UsdPhysics, Gf

def build_stage(num_colliders=40):
    s = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(s, UsdGeom.Tokens.z)
    world = UsdGeom.Xform.Define(s, "/World")
    # one rigid body with MANY mesh colliders beneath it (the trigger for PR#4002 race)
    body = UsdGeom.Xform.Define(s, "/World/Body")
    UsdPhysics.RigidBodyAPI.Apply(body.GetPrim())
    UsdPhysics.MassAPI.Apply(body.GetPrim())
    for i in range(num_colliders):
        m = UsdGeom.Mesh.Define(s, f"/World/Body/col_{i}")
        # minimal cube mesh
        m.CreatePointsAttr([Gf.Vec3f(-1,-1,-1),Gf.Vec3f(1,-1,-1),Gf.Vec3f(1,1,-1),Gf.Vec3f(-1,1,-1),
                            Gf.Vec3f(-1,-1,1),Gf.Vec3f(1,-1,1),Gf.Vec3f(1,1,1),Gf.Vec3f(-1,1,1)])
        m.CreateFaceVertexCountsAttr([4,4,4,4,4,4])
        m.CreateFaceVertexIndicesAttr([0,1,2,3, 4,5,6,7, 0,1,5,4, 2,3,7,6, 0,3,7,4, 1,2,6,5])
        UsdGeom.Xformable(m).AddTranslateOp().Set(Gf.Vec3d(i*2.0,0,0))
        UsdPhysics.CollisionAPI.Apply(m.GetPrim())
        UsdPhysics.MeshCollisionAPI.Apply(m.GetPrim())
    return s

def main():
    n_iters = int(os.environ.get("N","50"))
    n_col = int(os.environ.get("COLLIDERS","40"))
    s = build_stage(n_col)
    flat = Usd.Stage.Open(s.Flatten())
    fn = getattr(UsdPhysics,"LoadUsdPhysicsFromRange",None) or getattr(UsdPhysics,"UsdPhysicsLoadStageFromPrimRange")
    print(f"USD {Usd.GetVersion()}  colliders={n_col} iters={n_iters} threads={os.environ.get('PXR_WORK_THREAD_LIMIT','auto')}", flush=True)
    for i in range(n_iters):
        fn(flat, ["/World"], excludePaths=[])
    print("COMPLETED", n_iters, flush=True)

if __name__ == "__main__":
    main()
