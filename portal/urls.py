from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="portal/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="portal:login"), name="logout"),

    path("", views.home, name="home"),

    path("eventos/", views.evento_list, name="evento_list"),
    path("eventos/novo/", views.evento_create, name="evento_create"),
    path("eventos/<int:pk>/", views.evento_detail, name="evento_detail"),
    path("eventos/<int:pk>/editar/", views.evento_edit, name="evento_edit"),

    path("mentorias/", views.mentoria_list, name="mentoria_list"),
    path("mentorias/nova/", views.mentoria_create, name="mentoria_create"),
    path("mentorias/<int:pk>/", views.mentoria_detail, name="mentoria_detail"),

    path("pessoas/", views.pessoa_list, name="pessoa_list"),
    path("pessoas/nova/", views.pessoa_create, name="pessoa_create"),
    path("pessoas/<int:pk>/", views.pessoa_detail, name="pessoa_detail"),

    path("projetos/", views.projeto_list, name="projeto_list"),
    path("projetos/<int:pk>/", views.projeto_detail, name="projeto_detail"),
]
