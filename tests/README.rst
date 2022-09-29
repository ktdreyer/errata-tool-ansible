Unit-testing Ansible modules is complicated.

You can test some small methods easily enough, but you will soon want to test
larger methods, including the ``main()`` method.

Remember, Ansible runs modules on nodes. Each module runs in an individual
unix process, and it exits with an exit code and a bit of JSON.

For Python Ansible modules (like errata-tool-ansible's modules), we call the
Ansible APIs ``module.exit_json()`` or ``module.fail_json()`` at the end.
These methods will effectively quit the Python process, so we need a way to
handle that in unit tests.

To unit test code that calls ``module.exit_json()`` or ``module.fail_json()``,
I've written fake methods in ``tests/utils.py``, intended for monkeypatching.
These fakes will raise with the called values.

* If I expect ``main()`` to exit with a successful exit status, then I use
  ``with pytest.raises(AnsibleExitJson) as ex:``
* If I expect ``main()`` to exit with a failure, then I use with
  ``pytest.raises(AnsibleFailJson) as ex:``

Look at existing unit tests for examples of how to do this.
