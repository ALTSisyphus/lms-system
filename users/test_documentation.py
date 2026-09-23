from rest_framework.test import APITestCase


class DocumentationTests(APITestCase):
    def test_documentation_available_anonymously(self):
        for url in ["/api/schema/", "/api/docs/", "/api/redoc/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_schema_matches_payment_subscription_and_list_contracts(self):
        response = self.client.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        paths = schema["paths"]
        for path in ["/api/token/", "/api/token/refresh/", "/api/users/register/",
                     "/api/users/", "/api/users/{id}/", "/api/courses/", "/api/courses/{id}/",
                     "/api/lessons/", "/api/lessons/{id}/", "/api/subscriptions/",
                     "/api/payments/", "/api/payments/{id}/status/"]:
            self.assertIn(path, paths)
        payment_post = paths["/api/payments/"]["post"]
        self.assertEqual(set(payment_post["responses"]), {"201", "400", "401", "404", "502"})
        ref = payment_post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        request_schema = schema["components"]["schemas"][ref.split("/")[-1]]
        self.assertEqual(set(request_schema["properties"]), {"course"})
        self.assertFalse(payment_post.get("parameters"))
        self.assertIn({"jwtAuth": []}, payment_post["security"])
        self.assertEqual(schema["components"]["securitySchemes"]["jwtAuth"]["scheme"], "bearer")
        self.assertEqual(
            {p["name"] for p in paths["/api/payments/"]["get"]["parameters"]},
            {"paid_course", "paid_lesson", "payment_method", "ordering"},
        )
        self.assertEqual(
            {p["name"] for p in paths["/api/courses/"]["get"]["parameters"]},
            {"page", "page_size"},
        )
        params = paths["/api/payments/{id}/status/"]["get"]["parameters"]
        self.assertEqual([(p["name"], p["in"]) for p in params], [("id", "path")])
        self.assertEqual(set(paths["/api/subscriptions/"]["post"]["responses"]), {"200", "400", "401", "404"})
        payment_fields = schema["components"]["schemas"]["Payment"]["properties"]
        for field in ["paid_course", "paid_lesson"]:
            self.assertTrue(payment_fields[field]["nullable"])
        for field in ["stripe_product_id", "stripe_price_id", "stripe_session_id",
                      "payment_url", "payment_status"]:
            self.assertTrue(payment_fields[field]["readOnly"])
