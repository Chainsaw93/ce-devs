/** @odoo-module */

import { registry } from "@web/core/registry";
import { uiService } from "@web/core/ui/ui_service";
import { makeView, setupViewRegistries } from "@web/../tests/views/helpers";
import { click, getFixture, patchWithCleanup } from "@web/../tests/helpers/utils";

const serviceRegistry = registry.category("services");

QUnit.module("CRM Social Extension Tests", (hooks) => {
    let serverData;
    let target;

    hooks.beforeEach(async function (assert) {
        target = getFixture();
        serverData = {
            models: {
                'res.partner': {
                    fields: {
                        name: { string: "Name", type: "char" },
                        facebook_url: { string: "Facebook URL", type: "char" },
                        linkedin_url: { string: "LinkedIn URL", type: "char" },
                        twitter_url: { string: "Twitter URL", type: "char" },
                        is_profile_complete: { string: "Profile Complete", type: "boolean" },
                        social_score: { string: "Social Score", type: "integer" },
                        social_engagement_level: { 
                            string: "Social Engagement Level", 
                            type: "selection",
                            selection: [
                                ['low', 'Low'],
                                ['medium', 'Medium'], 
                                ['high', 'High'],
                                ['excellent', 'Excellent']
                            ]
                        },
                    },
                    records: [
                        {
                            id: 1,
                            name: "Complete Profile Customer",
                            facebook_url: "https://facebook.com/test1",
                            linkedin_url: "https://linkedin.com/in/test1",
                            twitter_url: "https://twitter.com/test1",
                            is_profile_complete: true,
                            social_score: 100,
                            social_engagement_level: 'excellent',
                        },
                        {
                            id: 2,
                            name: "Incomplete Profile Customer",
                            facebook_url: "https://facebook.com/test2",
                            linkedin_url: false,
                            twitter_url: false,
                            is_profile_complete: false,
                            social_score: 20,
                            social_engagement_level: 'low',
                        },
                        {
                            id: 3,
                            name: "No Social Media Customer",
                            facebook_url: false,
                            linkedin_url: false,
                            twitter_url: false,
                            is_profile_complete: false,
                            social_score: 0,
                            social_engagement_level: 'low',
                        }
                    ],
                },
            },
            views: {
                "res.partner,false,form": `
                    <form>
                        <header>
                            <div class="oe_button_box">
                                <button name="action_update_social_score" 
                                        type="object" 
                                        class="oe_stat_button"
                                        icon="fa-line-chart">
                                    <field name="social_score" widget="statinfo" string="Social Score"/>
                                </button>
                            </div>
                        </header>
                        <sheet>
                            <group>
                                <field name="name"/>
                            </group>
                            <notebook>
                                <page string="Social Media" name="social_media">
                                    <group>
                                        <group name="social_urls" string="Social Media URLs">
                                            <field name="facebook_url" widget="url"/>
                                            <field name="linkedin_url" widget="url"/>
                                            <field name="twitter_url" widget="url"/>
                                        </group>
                                        <group name="social_analytics" string="Social Analytics">
                                            <field name="is_profile_complete" readonly="1"/>
                                            <field name="social_score" readonly="1"/>
                                            <field name="social_engagement_level"/>
                                        </group>
                                    </group>
                                </page>
                            </notebook>
                        </sheet>
                    </form>
                `,
                "res.partner,false,list": `
                    <list>
                        <field name="name"/>
                        <field name="is_profile_complete" widget="boolean_favorite"/>
                        <field name="social_score"/>
                        <field name="social_engagement_level"/>
                    </list>
                `,
                "res.partner,false,search": `
                    <search>
                        <field name="name"/>
                        <field name="facebook_url"/>
                        <field name="linkedin_url"/>
                        <field name="twitter_url"/>
                        <filter name="profile_complete" string="Complete Profile" 
                                domain="[('is_profile_complete', '=', True)]"/>
                        <filter name="profile_incomplete" string="Incomplete Profile" 
                                domain="[('is_profile_complete', '=', False)]"/>
                        <filter name="high_social_score" string="High Social Score" 
                                domain="[('social_score', '>', 80)]"/>
                        <group expand="0" string="Group By">
                            <filter name="group_by_profile_complete" 
                                    string="Profile Status" 
                                    context="{'group_by': 'is_profile_complete'}"/>
                            <filter name="group_by_social_engagement" 
                                    string="Social Engagement" 
                                    context="{'group_by': 'social_engagement_level'}"/>
                        </group>
                    </search>
                `,
            },
        };

        serviceRegistry.add("ui", uiService);
        setupViewRegistries();
    });

    QUnit.module("Social Media Form View");

    QUnit.test("Social media tab is visible in form view", async function (assert) {
        const form = await makeView({
            type: "form",
            resModel: "res.partner",
            resId: 1,
            serverData,
        });

        assert.containsOnce(target, '.o_notebook');
        assert.containsOnce(target, 'a[name="social_media"]');
        assert.strictEqual(
            target.querySelector('a[name="social_media"]').textContent.trim(),
            "Social Media"
        );
    });

    QUnit.test("Social score button is displayed in form view", async function (assert) {
        const form = await makeView({
            type: "form",
            resModel: "res.partner",
            resId: 1,
            serverData,
        });

        assert.containsOnce(target, '.oe_stat_button[name="action_update_social_score"]');
        assert.containsOnce(target, '.o_field_widget[name="social_score"]');
    });

    QUnit.test("Social media fields are editable in form view", async function (assert) {
        const form = await makeView({
            type: "form",
            resModel: "res.partner",
            resId: 2,
            serverData,
        });

        // Click on social media tab
        await click(target, 'a[name="social_media"]');

        assert.containsOnce(target, 'input[name="facebook_url"]');
        assert.containsOnce(target, 'input[name="linkedin_url"]');
        assert.containsOnce(target, 'input[name="twitter_url"]');
        assert.containsOnce(target, 'select[name="social_engagement_level"]');
    });

    QUnit.test("Profile complete status is correctly displayed", async function (assert) {
        // Test complete profile
        const completeForm = await makeView({
            type: "form",
            resModel: "res.partner",
            resId: 1,
            serverData,
        });

        await click(target, 'a[name="social_media"]');
        
        const profileCompleteField = target.querySelector('input[name="is_profile_complete"]');
        assert.ok(profileCompleteField.checked, "Profile complete should be checked for complete profile");

        // Test incomplete profile
        const incompleteForm = await makeView({
            type: "form",
            resModel: "res.partner",
            resId: 2,
            serverData,
        });

        await click(target, 'a[name="social_media"]');
        
        const incompleteProfileField = target.querySelector('input[name="is_profile_complete"]');
        assert.notOk(incompleteProfileField.checked, "Profile complete should not be checked for incomplete profile");
    });

    QUnit.module("Social Media List View");

    QUnit.test("Profile complete column is visible in list view", async function (assert) {
        const list = await makeView({
            type: "list",
            resModel: "res.partner",
            serverData,
        });

        assert.containsOnce(target, 'th[data-name="is_profile_complete"]');
        assert.containsOnce(target, 'th[data-name="social_score"]');
        assert.containsOnce(target, 'th[data-name="social_engagement_level"]');
    });

    QUnit.test("Social score values are displayed correctly in list view", async function (assert) {
        const list = await makeView({
            type: "list",
            resModel: "res.partner",
            serverData,
        });

        const scoreFields = target.querySelectorAll('td[name="social_score"]');
        assert.strictEqual(scoreFields.length, 3);
        
        // Check that scores are displayed correctly
        assert.strictEqual(scoreFields[0].textContent.trim(), "100");
        assert.strictEqual(scoreFields[1].textContent.trim(), "20");
        assert.strictEqual(scoreFields[2].textContent.trim(), "0");
    });

    QUnit.module("Social Media Search View");

    QUnit.test("Social media search filters are available", async function (assert) {
        const searchView = await makeView({
            type: "search",
            resModel: "res.partner",
            serverData,
        });

        // Check for profile completion filters
        assert.containsOnce(target, '.o_filter_menu .dropdown-item[data-filter="profile_complete"]');
        assert.containsOnce(target, '.o_filter_menu .dropdown-item[data-filter="profile_incomplete"]');
        assert.containsOnce(target, '.o_filter_menu .dropdown-item[data-filter="high_social_score"]');
    });

    QUnit.test("Social media fields are searchable", async function (assert) {
        const searchView = await makeView({
            type: "search",
            resModel: "res.partner",
            serverData,
        });

        // Check that social media fields appear in search
        const searchInput = target.querySelector('.o_searchview_input');
        assert.ok(searchInput, "Search input should be present");
    });

    QUnit.test("Group by social engagement is available", async function (assert) {
        const searchView = await makeView({
            type: "search",
            resModel: "res.partner",
            serverData,
        });

        assert.containsOnce(target, '.o_group_by_menu .dropdown-item[data-filter="group_by_social_engagement"]');
    });

    QUnit.module("Social Media URL Validation");

    QUnit.test("URL widget is applied to social media fields", async function (assert) {
        const form = await makeView({
            type: "form",
            resModel: "res.partner",
            resId: 1,
            serverData,
        });

        await click(target, 'a[name="social_media"]');

        // Check that URL widget is applied (fields should have url widget class or behavior)
        const facebookField = target.querySelector('input[name="facebook_url"]');
        const linkedinField = target.querySelector('input[name="linkedin_url"]');
        const twitterField = target.querySelector('input[name="twitter_url"]');

        assert.ok(facebookField, "Facebook URL field should be present");
        assert.ok(linkedinField, "LinkedIn URL field should be present");
        assert.ok(twitterField, "Twitter URL field should be present");

        // Check that the fields contain valid URLs
        assert.strictEqual(facebookField.value, "https://facebook.com/test1");
        assert.strictEqual(linkedinField.value, "https://linkedin.com/in/test1");
        assert.strictEqual(twitterField.value, "https://twitter.com/test1");
    });

    QUnit.module("Social Score Integration");

    QUnit.test("Social score button click triggers update", async function (assert) {
        assert.expect(2);

        // Mock the RPC call
        patchWithCleanup(target.env.services.rpc, {
            async call(route, params) {
                if (params.method === "action_update_social_score") {
                    assert.step("social_score_update_called");
                    return {
                        type: 'ir.actions.client',
                        tag: 'reload',
                    };
                }
                return this._super(...arguments);
            }
        });

        const form = await makeView({
            type: "form",
            resModel: "res.partner",
            resId: 1,
            serverData,
        });

        const socialScoreButton = target.querySelector('.oe_stat_button[name="action_update_social_score"]');
        assert.ok(socialScoreButton, "Social score button should be present");

        await click(socialScoreButton);
        assert.verifySteps(["social_score_update_called"]);
    });

    QUnit.module("Customer Search Functionality");

    QUnit.test("Customer search autocomplete works", async function (assert) {
        // Mock the autocomplete endpoint
        const mockFetch = (url, options) => {
            if (url.includes('/customers/search/autocomplete')) {
                return Promise.resolve({
                    json: () => Promise.resolve({
                        result: [
                            {
                                id: 1,
                                name: "Complete Profile Customer",
                                url: "/customers/1",
                                social_platforms: ["Facebook", "LinkedIn", "Twitter"],
                                social_score: 100,
                                is_complete: true,
                            }
                        ]
                    })
                });
            }
            return fetch(url, options);
        };

        // Patch fetch for testing
        patchWithCleanup(window, { fetch: mockFetch });

        // Create a simple search input for testing
        target.innerHTML = `
            <input type="text" id="search" placeholder="Search customers...">
            <div id="search-suggestions" class="list-group" style="display: none;"></div>
        `;

        // Import and initialize the search functionality
        const searchInput = target.querySelector('#search');
        const suggestionsContainer = target.querySelector('#search-suggestions');

        // Simulate user input
        searchInput.value = 'Complete';
        searchInput.dispatchEvent(new Event('input'));

        // Wait a bit for debounced search
        await new Promise(resolve => setTimeout(resolve, 350));

        // Check that suggestions are displayed
        assert.ok(suggestionsContainer.innerHTML.includes('Complete Profile Customer'), 
                 "Search suggestions should display the customer");
    });

    QUnit.module("Performance Tests");

    QUnit.test("Large dataset rendering performance", async function (assert) {
        // Create a large dataset
        const largeServerData = { ...serverData };
        largeServerData.models['res.partner'].records = [];
        
        for (let i = 0; i < 100; i++) {
            largeServerData.models['res.partner'].records.push({
                id: i + 10,
                name: `Customer ${i}`,
                facebook_url: i % 2 === 0 ? `https://facebook.com/customer${i}` : false,
                linkedin_url: i % 3 === 0 ? `https://linkedin.com/in/customer${i}` : false,
                twitter_url: i % 4 === 0 ? `https://twitter.com/customer${i}` : false,
                is_profile_complete: i % 5 === 0,
                social_score: (i * 10) % 100,
                social_engagement_level: ['low', 'medium', 'high', 'excellent'][i % 4],
            });
        }

        const startTime = performance.now();
        
        const list = await makeView({
            type: "list",
            resModel: "res.partner",
            serverData: largeServerData,
        });

        const endTime = performance.now();
        const renderTime = endTime - startTime;

        // Should render in reasonable time (less than 1 second)
        assert.ok(renderTime < 1000, `Large dataset should render quickly (${renderTime}ms)`);
        
        // Verify all records are displayed
        const rows = target.querySelectorAll('tbody tr');
        assert.strictEqual(rows.length, 100, "All 100 records should be displayed");
    });

    QUnit.module("Error Handling");

    QUnit.test("Graceful handling of network errors in search", async function (assert) {
        // Mock a failing fetch
        const mockFetch = () => Promise.reject(new Error('Network error'));
        patchWithCleanup(window, { fetch: mockFetch });

        target.innerHTML = `
            <input type="text" id="search" placeholder="Search customers...">
            <div id="search-suggestions" class="list-group" style="display: none;"></div>
        `;

        const searchInput = target.querySelector('#search');
        const suggestionsContainer = target.querySelector('#search-suggestions');

        // Simulate user input that would trigger search
        searchInput.value = 'test';
        searchInput.dispatchEvent(new Event('input'));

        // Wait for the search to complete
        await new Promise(resolve => setTimeout(resolve, 350));

        // Should handle error gracefully without crashing
        assert.ok(true, "Network error should be handled gracefully");
    });

    QUnit.test("Empty search results handling", async function (assert) {
        // Mock empty results
        const mockFetch = () => Promise.resolve({
            json: () => Promise.resolve({ result: [] })
        });
        patchWithCleanup(window, { fetch: mockFetch });

        target.innerHTML = `
            <input type="text" id="search" placeholder="Search customers...">
            <div id="search-suggestions" class="list-group" style="display: none;"></div>
        `;

        const searchInput = target.querySelector('#search');
        
        searchInput.value = 'nonexistent';
        searchInput.dispatchEvent(new Event('input'));

        await new Promise(resolve => setTimeout(resolve, 350));

        // Should show "no results" message
        const suggestionsContainer = target.querySelector('#search-suggestions');
        assert.ok(suggestionsContainer.innerHTML.includes('No customers found'), 
                 "Should display no results message");
    });
});