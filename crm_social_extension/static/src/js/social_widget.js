/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field";
import { IntegerField } from "@web/views/fields/integer/integer_field";
import { BooleanField } from "@web/views/fields/boolean/boolean_field";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * Social URL Field
 */
class SocialUrlField extends CharField {
    setup() {
        super.setup();
        this.notification = useService("notification");
        this.rpc = useService("rpc");
        this.state = useState({
            isValidating: false,
            isValid: true,
            previewData: null,
        });
    }

    get socialPlatform() {
        const fieldName = this.props.name || "";
        if (fieldName.includes("facebook")) return "facebook";
        if (fieldName.includes("linkedin")) return "linkedin";
        if (fieldName.includes("twitter")) return "twitter";
        return null;
    }

    get platformConfig() {
        const configs = {
            facebook: {
                name: "Facebook",
                icon: "fa-facebook",
                color: "#1877f2",
                pattern: /^https?:\/\/(www\.)?(facebook|fb)\.com\/.+/i,
            },
            linkedin: {
                name: "LinkedIn",
                icon: "fa-linkedin",
                color: "#0077b5",
                pattern: /^https?:\/\/(www\.)?linkedin\.com\/(in|company)\/.+/i,
            },
            twitter: {
                name: "Twitter",
                icon: "fa-twitter",
                color: "#1da1f2",
                pattern: /^https?:\/\/(www\.)?(twitter|x)\.com\/.+/i,
            },
        };
        return configs[this.socialPlatform] || {};
    }

    async validateUrl(url) {
        if (!url) {
            this.state.isValid = true;
            this.state.previewData = null;
            return;
        }

        this.state.isValidating = true;
        try {
            const config = this.platformConfig;
            if (config.pattern && !config.pattern.test(url)) {
                this.state.isValid = false;
                this.notification.add(
                    _t("Please enter a valid %s URL", config.name || "social"),
                    { type: "warning" }
                );
            } else {
                this.state.isValid = true;
                await this.fetchPreviewData(url);
            }
        } catch (error) {
            console.error("URL validation error:", error);
            this.state.isValid = false;
        } finally {
            this.state.isValidating = false;
        }
    }

    async fetchPreviewData(url) {
        try {
            const payload = {
                model: "res.partner",
                method: "get_social_preview",
                args: [url],
                kwargs: {},
            };
            const response = await this.rpc("/web/dataset/call_kw", payload);
            if (response) {
                this.state.previewData = response;
            }
        } catch (error) {
            // Silenciar: es sólo un “nice to have”
            console.debug("Preview fetch failed:", error);
        }
    }

    async onChange(value) {
        await super.onChange(value);
        await this.validateUrl(value);
    }

    get classNames() {
        const classes = super.classNames || {};
        return {
            ...classes,
            o_field_social_url: true,
            [`o_field_social_${this.socialPlatform}`]: !!this.socialPlatform,
            o_field_invalid: !this.state.isValid,
            o_field_validating: this.state.isValidating,
        };
    }
}
SocialUrlField.template = "crm_social_extension.SocialUrlField";

/**
 * Social Score Field
 */
class SocialScoreField extends IntegerField {
    setup() {
        super.setup();
        this.state = useState({ animatedValue: 0, isAnimating: false });
        this._raf = null;

        onMounted(() => this.animateScore());
        onWillUnmount(() => {
            if (this._raf) cancelAnimationFrame(this._raf);
        });
    }

    animateScore() {
        if (this.state.isAnimating) return;

        const targetValue = this.props.value || 0;
        const startValue = this.state.animatedValue;
        const duration = 1000;
        const startTime = performance.now();
        this.state.isAnimating = true;

        const tick = (now) => {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const easeOut = 1 - Math.pow(1 - progress, 3);
            this.state.animatedValue = Math.round(
                startValue + (targetValue - startValue) * easeOut
            );
            if (progress < 1) {
                this._raf = requestAnimationFrame(tick);
            } else {
                this.state.isAnimating = false;
            }
        };

        this._raf = requestAnimationFrame(tick);
    }

    get scoreLevel() {
        const score = this.props.value || 0;
        if (score >= 80) return "excellent";
        if (score >= 60) return "good";
        if (score >= 40) return "fair";
        if (score > 0) return "poor";
        return "none";
    }

    get scoreLevelConfig() {
        const configs = {
            excellent: { color: "#28a745", label: "Excellent", icon: "fa-star" },
            good: { color: "#17a2b8", label: "Good", icon: "fa-thumbs-up" },
            fair: { color: "#ffc107", label: "Fair", icon: "fa-meh" },
            poor: { color: "#fd7e14", label: "Poor", icon: "fa-exclamation-triangle" },
            none: { color: "#dc3545", label: "No Score", icon: "fa-times" },
        };
        return configs[this.scoreLevel];
    }

    get progressPercentage() {
        return Math.min(this.props.value || 0, 100);
    }
}
SocialScoreField.template = "crm_social_extension.SocialScoreField";

/**
 * Profile Complete Field
 */
class ProfileCompleteField extends BooleanField {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = useState({ missingPlatforms: [] });

        onMounted(async () => {
            await this.calculateMissingPlatforms();
        });
    }

    async calculateMissingPlatforms() {
        const resId = this.props.record?.resId;
        if (!resId) return;

        try {
            const partner = await this.orm.read("res.partner", [resId], [
                "facebook_url",
                "linkedin_url",
                "twitter_url",
            ]);

            if (partner?.length) {
                const p = partner[0];
                const missing = [];
                if (!p.facebook_url) missing.push("Facebook");
                if (!p.linkedin_url) missing.push("LinkedIn");
                if (!p.twitter_url) missing.push("Twitter");
                this.state.missingPlatforms = missing;
            }
        } catch (error) {
            console.error("Error calculating missing platforms:", error);
        }
    }

    get completionPercentage() {
        const total = 3;
        const complete = total - this.state.missingPlatforms.length;
        return Math.round((complete / total) * 100);
    }
}
ProfileCompleteField.template = "crm_social_extension.ProfileCompleteField";

/**
 * Social Media Dashboard (componente genérico)
 */
class SocialMediaDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ socialData: {}, activities: [], isLoading: true });

        onMounted(async () => {
            await this.loadSocialData();
        });
    }

    async loadSocialData() {
        const resId = this.props.resId;
        if (!resId) {
            this.state.isLoading = false;
            return;
        }
        try {
            const [partner, activities] = await Promise.all([
                this.orm.read("res.partner", [resId], [
                    "name",
                    "facebook_url",
                    "linkedin_url",
                    "twitter_url",
                    "social_score",
                    "is_profile_complete",
                    "social_engagement_level",
                    "social_notes",
                    "last_social_update",
                ]),
                // Usar res_model (char) en vez de res_model_id
                this.orm.searchRead(
                    "mail.activity",
                    [["res_model", "=", "res.partner"], ["res_id", "=", resId], ["activity_type_id.name", "ilike", "social"]],
                    ["subject", "summary", "date_deadline", "state"]
                ),
            ]);

            this.state.socialData = partner[0] || {};
            this.state.activities = activities;
        } catch (error) {
            console.error("Error loading social data:", error);
            this.notification.add(_t("Error loading social media data"), { type: "danger" });
        } finally {
            this.state.isLoading = false;
        }
    }

    get socialPlatforms() {
        const d = this.state.socialData || {};
        return [
            { name: "Facebook", url: d.facebook_url, icon: "fa-facebook", color: "#1877f2", present: !!d.facebook_url },
            { name: "LinkedIn", url: d.linkedin_url, icon: "fa-linkedin", color: "#0077b5", present: !!d.linkedin_url },
            { name: "Twitter", url: d.twitter_url, icon: "fa-twitter", color: "#1da1f2", present: !!d.twitter_url },
        ];
    }
}
SocialMediaDashboard.template = "crm_social_extension.SocialMediaDashboard";

/** Registry (form fields) — Odoo 18 requiere objeto con { component: … } */
registry.category("fields").add("social_url", {
    component: SocialUrlField,
    displayName: _t("Social URL"),
    supportedTypes: ["char"],
});

registry.category("fields").add("social_score", {
    component: SocialScoreField,
    displayName: _t("Social Score"),
    supportedTypes: ["integer", "float"],
});

registry.category("fields").add("profile_complete", {
    component: ProfileCompleteField,
    displayName: _t("Profile Complete"),
    supportedTypes: ["boolean"],
});

// Si quieres usar el dashboard como widget de campo (p.ej. en un <field> vacío),
// puedes registrarlo también como field widget:
registry.category("fields").add("social_media_dashboard", {
    component: SocialMediaDashboard,
    displayName: _t("Social Media Dashboard"),
    // lo podrás montar sobre un campo dummy (char/text/html)
    supportedTypes: ["char", "text", "html"],
});

console.log("CRM Social Extension widgets loaded successfully (v18)");
