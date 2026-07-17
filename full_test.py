#!/opt/anaconda3/envs/securityspy/bin/python

from google_nest_camera_proxy import run
import sentry_sdk

sentry_sdk.init(
    dsn="https://467a99ecfb555a813fe7f01f30c99173@o4505856774963200.ingest.sentry.io/4505856790888448",
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=1.0,
    # Set profiles_sample_rate to 1.0 to profile 100%
    # of sampled transactions.
    # We recommend adjusting this value in production.
    profiles_sample_rate=1.0,
)

run()
