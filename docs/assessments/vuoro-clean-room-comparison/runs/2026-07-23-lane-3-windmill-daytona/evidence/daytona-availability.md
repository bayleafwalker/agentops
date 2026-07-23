# Lane 3 — Daytona Availability Boundary

The locked public Daytona source is `ec4c21b2d597091ac09ecc278f3bcc172575a987`.
Its README states that core development moved to a private codebase and that
the documented Python quick start begins by creating an account and generating
an API key. Those prerequisites were not available in the locked disposable
corpus, and no user or production credential was requested or used.

This is an availability and reproducibility finding, not a product-security
verdict. It means the exercise cannot credit Daytona for sandbox isolation,
secret handling, identity resolution, pause/restore, or R6 without a separate
authorized hosted-account test. The public source’s maintenance status also
means its pinned behavior should not be extrapolated to the current private
product.
