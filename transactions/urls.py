from django.urls import include,path
from . import views

urlpatterns = [
    path("", views.starting_page, name="starting-page"),
    path("load_configuration/", views.load_configuration, name="load_configuration"),
    path("update_transactions/", views.update_transactions, name="update_transactions"),
]