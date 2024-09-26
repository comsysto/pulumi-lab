from pulumi import export, ResourceOptions
import pulumi_aws as aws

# Define a prefix
prefix = "pulumi-lab"

# Helper function to add prefix
def prefixed(name):
    return f"{prefix}-{name}"

# Define a helper function to create tags
def create_tags(name):
    return {
        "Name": prefixed(name),
        "Project": "PulumiLab"
    }

# Define a resource group
resource_group = aws.resourcegroups.Group("resource-group",
    name=(prefixed("resource-group")),
    resource_query=aws.resourcegroups.GroupResourceQueryArgs(
        query="""
            {
                "ResourceTypeFilters": ["AWS::AllSupported"],
                "TagFilters": [
                    {
                        "Key": "Project",
                        "Values": ["PulumiLab"]
                    }
                ]
            }
        """
    ),
    tags=create_tags("resource-group")
)

# Create a new VPC
vpc = aws.ec2.Vpc("vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags=create_tags("vpc")
)

# Create a single subnet
subnet = aws.ec2.Subnet("public-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    availability_zone="eu-central-1a",  # Adjust as needed
    tags=create_tags("public-subnet")
)

# Create an internet gateway
internet_gateway = aws.ec2.InternetGateway("internet-gateway",
    vpc_id=vpc.id,
    tags=create_tags("internet-gateway")
)

# Create a route table
route_table = aws.ec2.RouteTable("route-table",
    vpc_id=vpc.id,
    routes=[{
        "cidr_block": "0.0.0.0/0",
        "gateway_id": internet_gateway.id
    }],
    tags=create_tags("route-table")
)

# Associate the single subnet with the route table
route_table_association = aws.ec2.RouteTableAssociation("route-table-assoc",
    subnet_id=subnet.id,
    route_table_id=route_table.id
)