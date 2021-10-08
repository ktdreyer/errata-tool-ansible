errata-tool-ansible
===================

.. image:: https://github.com/ktdreyer/errata-tool-ansible/workflows/tests/badge.svg
             :target: https://github.com/ktdreyer/errata-tool-ansible/actions

.. image:: https://codecov.io/gh/ktdreyer/errata-tool-ansible/branch/master/graph/badge.svg
             :target: https://codecov.io/gh/ktdreyer/errata-tool-ansible

.. image:: https://img.shields.io/badge/dynamic/json?style=flat&label=galaxy&prefix=v&url=https://galaxy.ansible.com/api/v2/collections/ktdreyer/errata_tool_ansible/&query=latest_version.version
             :target: https://galaxy.ansible.com/ktdreyer/errata_tool_ansible

Ansible modules to manage Errata Tool resources.

This is not about installing the Errata Tool. Instead, it is a way to
declaratively define things within Errata Tool, where you might normally use
the Errata Tool UI.

errata_tool_product
-------------------

The ``errata_tool_product`` module can create or update products within the
Errata Tool.

.. code-block:: yaml

    - name: Add RHCEPH product
      errata_tool_product:
        short_name: RHCEPH
        name: Red Hat Ceph Storage
        description: Red Hat Ceph Storage
        bugzilla_product_name: ""
        valid_bug_states:
          - ASSIGNED
          - MODIFIED
          - NEW
          - ON_DEV
          - ON_QA
          - POST
          - VERIFIED
        active: true
        ftp_subdir: RHCEPH
        internal: false
        default_docs_reviewer: docs-errata-list@redhat.com
        push_targets:
          - ftp
          - cdn_stage
          - cdn_docker_stage
          - cdn_docker
          - cdn
        default_solution: enterprise
        state_machine_rule_set: Default
        move_bugs_on_qe: false


errata_tool_product_version
---------------------------

The ``errata_tool_product_version`` module can create or update Product
Versions within the Errata Tool.

.. code-block:: yaml

    - name: Add RHCEPH 4.0 RHEL 8 Product Version
      errata_tool_product_version:
        product: RHCEPH
        name: RHCEPH-4.0-RHEL-8
        description: Red Hat Ceph Storage 4.0
        default_brew_tag: ceph-4.0-rhel-8-candidate
        allow_rhn_debuginfo: false
        is_oval_product: false
        is_rhel_addon: false
        is_server_only: false
        rhel_release_name: RHEL-8
        sig_key_name: redhatrelease2
        allow_buildroot_push: false
        push_targets:
          - ftp
          - cdn_stage
          - cdn_docker_stage
          - cdn_docker
          - cdn

errata_tool_release
-------------------

The ``errata_tool_release`` module can create or update Releases within the
Errata Tool.

.. code-block:: yaml

    - name: Add rhceph-4.0 release
      errata_tool_release:
        product: RHCEPH
        name: rhceph-4.0
        type: QuarterlyUpdate
        description: Red Hat Ceph Storage 4.0
        product_versions:
          - RHCEPH-4.0-RHEL-8
          - RHEL-7-RHCEPH-4.0
        enabled: true
        active: true
        enable_batching: false
        program_manager: coolmanager@redhat.com
        blocker_flags:
          - ceph-4
        internal_target_release: ""
        zstream_target_release: null
        ship_date: '2020-01-31'
        allow_shadow: false
        allow_blocker: false
        allow_exception: false
        allow_pkg_dupes: true
        supports_component_acl: true
        limit_bugs_by_product: false
        state_machine_rule_set: null
        pelc_product_version: null
        brew_tags: []


errata_tool_variant
-------------------

The ``errata_tool_variant`` module can create or update Variants within the
Errata Tool.

.. code-block:: yaml

    - name: Add RHCEPH 4.0 Tools variant
      errata_tool_variant:
        name: 8Base-RHCEPH-4.0-Tools
        description: Red Hat Ceph Storage 4.0 Tools
        cpe: "cpe:/a:redhat:ceph_storage:4::el8"
        enabled: true
        buildroot: false
        product_version: RHCEPH-4.0-RHEL-8
        rhel_variant: 8Base
        push_targets: []

errata_tool_cdn_repo
--------------------

The ``errata_tool_cdn_repo`` module can create or update CDN Repos within the
Errata Tool.

.. code-block:: yaml

    - name: Add redhat-rhceph-rhceph-4-rhel8 cdn repo
      errata_tool_cdn_repo:
        name: redhat-rhceph-rhceph-4-rhel8
        release_type: Primary
        content_type: Docker
        variants:
          - 8Base-RHCEPH-4.0-Tools
        packages:
          rhceph-container:
            - latest
            - "{% raw %}{{version}}{% endraw %}"
            - "{% raw %}{{version}}-{{release}}{% endraw %}"

Note that if you want to use a tag string like ``{{version}}`` for your
package, you must escape the double brackets for Ansible with the
``{% raw %} ... {% endraw %}`` syntax. If you pass the values into Ansible
Tower's REST API, you may not need to escape the values like this.

errata_tool_user
----------------

The ``errata_tool_user`` module can create or update Users within the Errata
Tool.

.. code-block:: yaml

    - name: Add program manager Errata Tool account
      errata_tool_user:
        login_name: coolprogrammanager@redhat.com
        realname: Cool ProgramManager
        organization: Program Management
        receives_mail: false
        roles:
          - pm


errata_tool_request
-------------------

The ``errata_tool_request`` module can perform low-level HTTP requests to
Errata Tool. This exposes the entire Errata Tool REST API to you directly.
It is like Ansible's core `uri
<https://docs.ansible.com/ansible/latest/modules/uri_module.html>`_
module, except this respects the ``ERRATA_TOOL_URL`` and ``ERRATA_TOOL_AUTH``
variables and can perform SPENEGO (GSSAPI) authentication.

Why would you use this module instead of the higher level modules like
``errata_tool_product``, ``errata_tool_user``, etc? This
``errata_tool_request`` module has two main uses-cases.

1. You may want to do something that the higher level modules do not yet
   support. It can be easier to use this module to quickly prototype out
   your ideas for what actions you need, and then write the Python code to
   do it in a better way later. If you find that you need to use
   ``errata_tool_request`` to achieve functionality that is not yet present in
   the other errata-tool-ansible modules, please file a Feature Request
   issue in GitHub with your use case.
2. You want to write some tests that verify ET's data at a very low
   level. For example, you may want to write an integration test to verify
   that you've set up your ET configuration in the way you expect.

Note that this module will always report "changed: true" every time, because
it simply sends the request to the ET server on every ansible run. This
module cannot understand if your chosen request actually "changes" anything.

.. code-block:: yaml

    - name: Make a raw HTTP API call
      errata_tool_request:
        path: /api/v1/user/cooldeveloper
      register: response

    - name: show the parsed JSON in the HTTP response
      debug:
        var: response.json

    - name: check one of the values in the JSON response
      assert:
        that:
          - response.json.login_name == 'cooldeveloper@redhat.com'

Installing errata-tool-ansible from Ansible Galaxy
--------------------------------------------------

We distribute errata-tool-ansible through the `Ansible Galaxy
<https://galaxy.ansible.com/ktdreyer/errata_tool_ansible>`_.

If you are using Ansible 2.9 or greater, you can `install
<https://docs.ansible.com/ansible/latest/user_guide/collections_using.html>`_
errata-tool-ansible like so::

  ansible-galaxy collection install ktdreyer.errata_tool_ansible

This will install the latest Git snapshot automatically. Use ``--force``
upgrade your installed version to the latest version.

Python dependencies
-------------------

These Ansible modules require the `requests-gssapi
<https://pypi.org/project/requests-gssapi/>`_ and `lxml
<https://pypi.org/project/lxml/>`_ Python libraries. You must install these
libraries on the host where Ansible will execute (typically localhost).

On RHEL 7::

    yum -y install python-requests-gssapi python-lxml

On RHEL 8+ and Fedora::

    yum -y install python3-requests-gssapi python3-lxml


Errata Tool environment
-----------------------
These modules operate on the production Errata Tool environment by default.
You must have a valid Kerberos ticket.

You can select another environment with the ``ERRATA_TOOL_URL`` environment
variable, like so::

  ERRATA_TOOL_URL=https://other.env/ ansible-playbook -v my-et-playbook.yml

You can disable GSSAPI (Kerberos) authentication with the ``ERRATA_TOOL_AUTH``
environment variable::

  ERRATA_TOOL_URL=https://other.env/ ERRATA_TOOL_AUTH=notkerberos ansible-playbook ...

You can use Ansible's ``environment`` setting with your tasks or playbooks.
Here's an example playbook that calls a custom role with those variables set:

.. code-block:: yaml

    - name: ensure ET configuration
      gather_facts: no
      hosts: localhost
      connection: local
      environment:
        ERRATA_TOOL_URL: https://other.env/
        ERRATA_TOOL_AUTH: notkerberos
      roles:
        - my-custom-et-role

There is no support for HTTP Basic auth at this time.

File paths
----------

These modules import ``common_errata_tool`` from the ``module_utils``
directory.

One easy way to arrange your Ansible files is to symlink the ``library`` and
``module_utils`` directories into the directory with your playbook.

For example, if you have a ``errata-tool.yml`` playbook that you run with
``ansible-playbook``, it should live alongside these ``library`` and
``module_utils`` directories::

    top
    ├── errata-tool.yml
    ├── module_utils
    └── library

and you should run the playbook like so::

   ansible-playbook errata-tool.yml

License
-------

This errata-tool-ansible project is licensed under the GPLv3-or-later to match
Ansible's license.


TODO
----

* Unit tests

* Integration tests
