---
layout: page
permalink: /repositories/
title: repositories
description: Software systems, data pipelines, and platform tooling for applications across cloud infrastructure, distributed systems, and applied AI for enterprise and science.
nav: true
nav_order: 4
---

{% if site.data.repositories.github_users and site.data.repositories.github_users.size > 0 %}

## GitHub users

<div class="repositories d-flex flex-wrap flex-md-row flex-column justify-content-between align-items-center">
  {% for user in site.data.repositories.github_users %}
    {% include repository/repo_user.liquid username=user %}
  {% endfor %}
</div>

---

{% if site.repo_trophies.enabled %}
{% for user in site.data.repositories.github_users %}
{% if site.data.repositories.github_users.size > 1 %}

  <h4>{{ user }}</h4>
  {% endif %}
  <div class="repositories d-flex flex-wrap flex-md-row flex-column justify-content-between align-items-center">
  {% include repository/repo_trophies.liquid username=user %}
  </div>

---

{% endfor %}
{% endif %}
{% endif %}

{% if site.data.repositories.github_repos %}

## GitHub repositories

<div class="repositories d-flex flex-wrap flex-md-row flex-column justify-content-between align-items-center">
  {% for repo in site.data.repositories.github_repos %}
    <div class="w-100 mb-3">
      {% if repo == 'gooooer/alan-pi-sensor-setup' %}
        <a class="d-inline-block" href="https://github.com/{{ repo }}">
          <img
            class="only-light"
            alt="{{ repo }}"
            src="https://img.shields.io/badge/github-gooooer%2Falan--pi--sensor--setup-0366d6?logo=github&logoColor=white&labelColor=24292e&color=0366d6"
          >
          <img
            class="only-dark"
            alt="{{ repo }}"
            src="https://img.shields.io/badge/github-gooooer%2Falan--pi--sensor--setup-58a6ff?logo=github&logoColor=24292e&labelColor=161b22&color=58a6ff"
          >
        </a>
        <p class="mt-2 mb-0 text-muted">
          This project supports research by <a href="https://orcid.org/0000-0001-5989-7527" target="_blank" rel="noopener">Dr. James Miksanek</a> at Louisiana State University at Alexandria, using Raspberry Pi-based environmental sensing (temperature, humidity, CO2, and spectral light) to study how Artificial Light at Night (ALAN) and climate conditions influence insect colony activity.
        </p>
      {% else %}
        {% include repository/repo.liquid repository=repo %}
      {% endif %}
    </div>
  {% endfor %}
</div>
{% endif %}
