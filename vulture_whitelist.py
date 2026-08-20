# Vulture whitelist.
#
# Names referenced here are reported as unused by vulture but are consumed
# through mechanisms vulture's static analysis cannot follow (for example
# pytest injecting a fixture by parameter name). Each reference marks the name
# as used so the scan stays clean. This file is parsed, never executed.

# pytest injects this fixture into test functions by parameter name; vulture
# sees the parameter as an unused variable.
reset_root_logging  # noqa: B018,F821
