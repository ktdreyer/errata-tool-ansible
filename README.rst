errata-tool-ansible
===================

.. image:: https://travis-ci.org/ktdreyer/errata-tool-ansible.svg?branch=master
             :target: https://travis-ci.org/ktdreyer/errata-tool-ansible

.. image:: https://coveralls.io/repos/github/ktdreyer/errata-tool-ansible/badge.svg
             :target: https://coveralls.io/github/ktdreyer/errata-tool-ansible

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
        text_only_advisories_require_dists: true


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
        rhel_release_name: rhel-8
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
``{% raw %} ... {% endraw %}`` syntax.

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


Python dependencies
-------------------

These Ansible modules require the `requests-gssapi
<https://pypi.org/project/requests-gssapi/>`_ and `lxml
<https://pypi.org/project/lxml/>`_ Python libraries. You must install these
libraries on the host where Ansible will execute (typically localhost).

On RHEL 7::

    yum -y install python-requests-gssapi python-lxml

On RHEL 8 and Fedora::

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
