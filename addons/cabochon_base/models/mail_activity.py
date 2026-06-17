from odoo import models
from odoo.exceptions import AccessError

_CABOCHON_ACTIVITY_MODELS = {
    "cabochon.production.request",
    "cabochon.material.transfer",
}


class MailActivity(models.Model):
    _inherit = "mail.activity"

    def _check_cabochon_assignee_access(self):
        if self.env.context.get("cabochon_activity_system_update"):
            return
        forbidden = self.filtered(
            lambda activity: activity.res_model in _CABOCHON_ACTIVITY_MODELS
            and activity.user_id
            and activity.user_id != self.env.user
        )
        if forbidden:
            raise AccessError("Выполнять, изменять или удалять активность может только ее исполнитель.")

    def write(self, vals):
        self._check_cabochon_assignee_access()
        return super().write(vals)

    def unlink(self):
        self._check_cabochon_assignee_access()
        return super().unlink()

    def action_done(self):
        self._check_cabochon_assignee_access()
        return super().action_done()

    def action_feedback(self, feedback=False, attachment_ids=None):
        self._check_cabochon_assignee_access()
        return super().action_feedback(feedback=feedback, attachment_ids=attachment_ids)

    def action_feedback_schedule_next(self, feedback=False, attachment_ids=None):
        self._check_cabochon_assignee_access()
        return super().action_feedback_schedule_next(feedback=feedback, attachment_ids=attachment_ids)

    def _action_done(self, feedback=False, attachment_ids=None):
        self._check_cabochon_assignee_access()
        return super()._action_done(feedback=feedback, attachment_ids=attachment_ids)
