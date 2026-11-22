from django.urls import path
from . import analytics, api

urlpatterns = [
    path("analytics/overview/", analytics.Overview.as_view()),
    path("auth/csrf/", api.Csrf.as_view()),
    path("auth/login/", api.Login.as_view()),
    path("auth/logout/", api.Logout.as_view()),
    path("auth/me/", api.Me.as_view()),
    path("doctors/", api.DoctorList.as_view()),
    path("patients/", api.PatientSearch.as_view()),
    path("appointments/", api.AppointmentListCreate.as_view()),
    path("appointments/<int:pk>/cancel/", api.AppointmentCancel.as_view()),
    path("queue/check-in/", api.CheckIn.as_view()),
    path("queue/<int:pk>/start/", api.QueueAction.as_view(action="start")),
    path("queue/<int:pk>/complete/", api.QueueAction.as_view(action="complete")),
    path("queue/<int:pk>/no-show/", api.QueueAction.as_view(action="no_show")),
    path("queue/doctor/<int:pk>/", api.DoctorQueue.as_view()),
    path("queue/entry/<int:pk>/", api.PatientQueuePosition.as_view()),
]
